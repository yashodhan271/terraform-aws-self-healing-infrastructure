import boto3
import os
import json
import time
import logging
import gc
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients with connection pooling and timeout settings
session = boto3.Session()
rds_client = session.client('rds', config=boto3.config.Config(
    connect_timeout=5,
    read_timeout=10,
    retries={'max_attempts': 3}
))
cloudwatch_client = session.client('cloudwatch')
sns_client = session.client('sns')

# Get environment variables
DB_INSTANCE_ID = os.environ.get('DB_INSTANCE_ID')
MAX_HEALING_ATTEMPTS = int(os.environ.get('MAX_HEALING_ATTEMPTS', 3))
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
ORIGINAL_INSTANCE_CLASS = os.environ.get('ORIGINAL_INSTANCE_CLASS')
ORIGINAL_ALLOCATED_STORAGE = int(os.environ.get('ORIGINAL_ALLOCATED_STORAGE', 0))
ORIGINAL_ENGINE_VERSION = os.environ.get('ORIGINAL_ENGINE_VERSION')
BACKUP_VERIFICATION = os.environ.get('BACKUP_VERIFICATION', 'false').lower() == 'true'

# Constants
RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds

def lambda_handler(event, context):
    """
    Main handler for RDS self-healing Lambda function.
    Handles both performance issues and configuration drift.
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Determine the type of event (performance issue or scheduled drift check)
    event_type = determine_event_type(event)
    
    # Get current instance details with retry logic
    instance_details = get_instance_details_with_retry(DB_INSTANCE_ID)
    if not instance_details:
        message = f"Unable to retrieve details for DB instance {DB_INSTANCE_ID} after multiple attempts"
        logger.error(message)
        send_notification(message)
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to retrieve instance details')
        }
    
    # Check healing attempts to avoid infinite loops
    healing_attempts = get_healing_attempts(instance_details)
    if healing_attempts >= MAX_HEALING_ATTEMPTS:
        message = f"Maximum healing attempts ({MAX_HEALING_ATTEMPTS}) reached for DB instance {DB_INSTANCE_ID}"
        logger.warning(message)
        send_notification(message)
        return {
            'statusCode': 429,
            'body': json.dumps('Maximum healing attempts reached')
        }
    
    # Handle the event based on its type
    if event_type == 'performance_issue':
        result = handle_performance_issue(instance_details, event, healing_attempts)
    elif event_type == 'config_drift':
        result = handle_config_drift(instance_details, healing_attempts)
    elif event_type == 'backup_verification':
        result = verify_backups(instance_details)
    else:
        result = {
            'statusCode': 400,
            'body': json.dumps('Unknown event type')
        }
    
    # Clean up memory to prevent leaks
    gc.collect()
    
    return result

def determine_event_type(event):
    """
    Determine whether this is a performance issue or a scheduled drift check.
    """
    # Check if this is a CloudWatch alarm event (performance issue)
    if 'detail-type' in event and event['detail-type'] == 'CloudWatch Alarm State Change':
        return 'performance_issue'
    
    # Otherwise, assume it's a scheduled drift check
    return 'config_drift'

def get_instance_details_with_retry(db_instance_id, max_retries=RETRY_COUNT):
    """
    Get details about the RDS instance with retry logic for transient failures.
    """
    retries = 0
    while retries < max_retries:
        try:
            response = rds_client.describe_db_instances(DBInstanceIdentifier=db_instance_id)
            if response['DBInstances']:
                return response['DBInstances'][0]
            return None
        except Exception as e:
            logger.warning(f"Error getting instance details (attempt {retries+1}/{max_retries}): {str(e)}")
            retries += 1
            if retries < max_retries:
                time.sleep(RETRY_DELAY)
    
    logger.error(f"Failed to get instance details after {max_retries} attempts")
    return None

def get_healing_attempts(instance_details):
    """
    Get the number of healing attempts from instance tags.
    """
    try:
        response = rds_client.list_tags_for_resource(
            ResourceName=instance_details['DBInstanceArn']
        )
        
        for tag in response.get('TagList', []):
            if tag['Key'] == 'HealingAttempts':
                try:
                    return int(tag['Value'])
                except ValueError:
                    return 0
        
        return 0
    except Exception as e:
        logger.error(f"Error getting healing attempts: {str(e)}")
        return 0

def increment_healing_attempts(instance_arn, current_attempts):
    """
    Increment the healing attempts counter in instance tags.
    """
    try:
        rds_client.add_tags_to_resource(
            ResourceName=instance_arn,
            Tags=[
                {
                    'Key': 'HealingAttempts',
                    'Value': str(current_attempts + 1)
                },
                {
                    'Key': 'LastHealed',
                    'Value': datetime.now().isoformat()
                }
            ]
        )
        return True
    except Exception as e:
        logger.error(f"Error incrementing healing attempts: {str(e)}")
        return False

def handle_performance_issue(instance_details, event, healing_attempts):
    """
    Handle a performance issue event.
    """
    db_instance_id = instance_details['DBInstanceIdentifier']
    db_instance_status = instance_details['DBInstanceStatus']
    
    logger.info(f"Handling performance issue for DB instance {db_instance_id} in status {db_instance_status}")
    
    # Get alarm details to determine the specific issue
    alarm_name = None
    alarm_details = {}
    
    if 'detail' in event and 'alarmName' in event['detail']:
        alarm_name = event['detail']['alarmName']
        
        # Extract more detailed metrics from the alarm
        if 'metrics' in event['detail']:
            alarm_details = event['detail']['metrics']
            logger.info(f"Extracted metrics from alarm: {json.dumps(alarm_details)}")
    
    # Increment healing attempts
    increment_healing_attempts(instance_details['DBInstanceArn'], healing_attempts)
    
    # Apply healing action based on instance status and alarm
    if db_instance_status == 'available':
        # Determine the appropriate action based on the alarm
        if alarm_name:
            if 'cpu-utilization' in alarm_name.lower():
                return handle_cpu_issue(db_instance_id, instance_details, alarm_details)
            elif 'free-storage-space' in alarm_name.lower():
                return handle_storage_issue(db_instance_id, instance_details, alarm_details)
            elif 'database-connections' in alarm_name.lower():
                return handle_connections_issue(db_instance_id, instance_details, alarm_details)
            elif 'memory' in alarm_name.lower():
                return handle_memory_issue(db_instance_id, instance_details, alarm_details)
            elif 'replica-lag' in alarm_name.lower():
                return handle_replica_lag_issue(db_instance_id, instance_details, alarm_details)
            elif 'io-utilization' in alarm_name.lower():
                return handle_io_issue(db_instance_id, instance_details, alarm_details)
        
        # If we can't determine the specific issue, try a reboot
        try:
            rds_client.reboot_db_instance(
                DBInstanceIdentifier=db_instance_id,
                ForceFailover=False
            )
            message = f"Rebooted DB instance {db_instance_id} due to performance issue"
            logger.info(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('DB instance reboot initiated')
            }
        except Exception as e:
            logger.error(f"Error rebooting DB instance: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to heal DB instance')
            }
    else:
        message = f"DB instance {db_instance_id} is in status {db_instance_status}, no healing action taken"
        logger.info(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('No healing action taken')
        }

def handle_cpu_issue(db_instance_id, instance_details, alarm_details=None):
    """
    Handle high CPU utilization by scaling up the instance if needed.
    """
    current_instance_class = instance_details['DBInstanceClass']
    
    # Get detailed CPU metrics if available
    cpu_utilization = None
    if alarm_details and 'cpu' in alarm_details:
        cpu_utilization = alarm_details['cpu']
        logger.info(f"CPU utilization details: {cpu_utilization}%")
    
    # Check if we can scale up the instance
    if current_instance_class != ORIGINAL_INSTANCE_CLASS and is_instance_class_larger(ORIGINAL_INSTANCE_CLASS, current_instance_class):
        # If the current instance is smaller than the original, scale back up
        try:
            rds_client.modify_db_instance(
                DBInstanceIdentifier=db_instance_id,
                DBInstanceClass=ORIGINAL_INSTANCE_CLASS,
                ApplyImmediately=True
            )
            message = f"Scaling up DB instance {db_instance_id} from {current_instance_class} to {ORIGINAL_INSTANCE_CLASS} due to high CPU"
            logger.info(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('DB instance scaling initiated')
            }
        except Exception as e:
            logger.error(f"Error scaling up DB instance: {str(e)}")
    
    # If we can't scale up or there was an error, try a reboot
    try:
        rds_client.reboot_db_instance(
            DBInstanceIdentifier=db_instance_id,
            ForceFailover=False
        )
        message = f"Rebooted DB instance {db_instance_id} due to high CPU utilization"
        logger.info(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('DB instance reboot initiated')
        }
    except Exception as e:
        logger.error(f"Error rebooting DB instance: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to heal DB instance')
        }

def handle_storage_issue(db_instance_id, instance_details, alarm_details=None):
    """
    Handle low storage space by increasing allocated storage.
    """
    current_allocated_storage = instance_details['AllocatedStorage']
    
    # Get detailed storage metrics if available
    free_storage = None
    if alarm_details and 'free_storage' in alarm_details:
        free_storage = alarm_details['free_storage']
        logger.info(f"Free storage details: {free_storage}GB")
    
    # Check if we need to increase storage
    if current_allocated_storage < ORIGINAL_ALLOCATED_STORAGE:
        # If the current storage is less than the original, scale back up
        try:
            rds_client.modify_db_instance(
                DBInstanceIdentifier=db_instance_id,
                AllocatedStorage=ORIGINAL_ALLOCATED_STORAGE,
                ApplyImmediately=True
            )
            message = f"Increasing storage for DB instance {db_instance_id} from {current_allocated_storage}GB to {ORIGINAL_ALLOCATED_STORAGE}GB due to low storage space"
            logger.info(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('DB instance storage increase initiated')
            }
        except Exception as e:
            logger.error(f"Error increasing DB instance storage: {str(e)}")
    elif current_allocated_storage == ORIGINAL_ALLOCATED_STORAGE:
        # If we're already at the original storage, increase by 20%
        new_storage = int(current_allocated_storage * 1.2)
        try:
            rds_client.modify_db_instance(
                DBInstanceIdentifier=db_instance_id,
                AllocatedStorage=new_storage,
                ApplyImmediately=True
            )
            message = f"Increasing storage for DB instance {db_instance_id} from {current_allocated_storage}GB to {new_storage}GB due to low storage space"
            logger.info(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('DB instance storage increase initiated')
            }
        except Exception as e:
            logger.error(f"Error increasing DB instance storage: {str(e)}")
    
    # If we can't increase storage or there was an error, notify
    message = f"Unable to increase storage for DB instance {db_instance_id}. Manual intervention required."
    logger.info(message)
    send_notification(message)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Manual intervention required for storage issue')
    }

def handle_connections_issue(db_instance_id, instance_details, alarm_details=None):
    """
    Handle high connection count by rebooting the instance.
    """
    # Get detailed connection metrics if available
    connections = None
    if alarm_details and 'connections' in alarm_details:
        connections = alarm_details['connections']
        logger.info(f"Connection count details: {connections}")
    
    try:
        rds_client.reboot_db_instance(
            DBInstanceIdentifier=db_instance_id,
            ForceFailover=False
        )
        message = f"Rebooted DB instance {db_instance_id} due to high connection count"
        logger.info(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('DB instance reboot initiated')
        }
    except Exception as e:
        logger.error(f"Error rebooting DB instance: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to heal DB instance')
        }

def handle_memory_issue(db_instance_id, instance_details, alarm_details=None):
    """
    Handle memory-related issues by scaling up or rebooting the instance.
    """
    current_instance_class = instance_details['DBInstanceClass']
    
    # Get detailed memory metrics if available
    memory_utilization = None
    if alarm_details and 'memory' in alarm_details:
        memory_utilization = alarm_details['memory']
        logger.info(f"Memory utilization details: {memory_utilization}%")
    
    # Check if we can scale up the instance
    if current_instance_class != ORIGINAL_INSTANCE_CLASS and is_instance_class_larger(ORIGINAL_INSTANCE_CLASS, current_instance_class):
        # If the current instance is smaller than the original, scale back up
        try:
            rds_client.modify_db_instance(
                DBInstanceIdentifier=db_instance_id,
                DBInstanceClass=ORIGINAL_INSTANCE_CLASS,
                ApplyImmediately=True
            )
            message = f"Scaling up DB instance {db_instance_id} from {current_instance_class} to {ORIGINAL_INSTANCE_CLASS} due to high memory usage"
            logger.info(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('DB instance scaling initiated')
            }
        except Exception as e:
            logger.error(f"Error scaling up DB instance: {str(e)}")
    
    # If we can't scale up or there was an error, try a reboot
    try:
        rds_client.reboot_db_instance(
            DBInstanceIdentifier=db_instance_id,
            ForceFailover=False
        )
        message = f"Rebooted DB instance {db_instance_id} due to high memory usage"
        logger.info(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('DB instance reboot initiated')
        }
    except Exception as e:
        logger.error(f"Error rebooting DB instance: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to heal DB instance')
        }

def handle_replica_lag_issue(db_instance_id, instance_details, alarm_details=None):
    """
    Handle replica lag issues by rebooting the replica.
    """
    # Get detailed replica lag metrics if available
    replica_lag = None
    if alarm_details and 'replica_lag' in alarm_details:
        replica_lag = alarm_details['replica_lag']
        logger.info(f"Replica lag details: {replica_lag} seconds")
    
    try:
        rds_client.reboot_db_instance(
            DBInstanceIdentifier=db_instance_id,
            ForceFailover=False
        )
        message = f"Rebooted DB replica {db_instance_id} due to high replica lag"
        logger.info(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('DB replica reboot initiated')
        }
    except Exception as e:
        logger.error(f"Error rebooting DB replica: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to heal DB replica')
        }

def handle_io_issue(db_instance_id, instance_details, alarm_details=None):
    """
    Handle I/O-related issues by optimizing or scaling up the instance.
    """
    current_instance_class = instance_details['DBInstanceClass']
    
    # Get detailed I/O metrics if available
    io_utilization = None
    if alarm_details and 'io' in alarm_details:
        io_utilization = alarm_details['io']
        logger.info(f"I/O utilization details: {io_utilization}%")
    
    # Check if we can scale up the instance
    if current_instance_class != ORIGINAL_INSTANCE_CLASS and is_instance_class_larger(ORIGINAL_INSTANCE_CLASS, current_instance_class):
        # If the current instance is smaller than the original, scale back up
        try:
            rds_client.modify_db_instance(
                DBInstanceIdentifier=db_instance_id,
                DBInstanceClass=ORIGINAL_INSTANCE_CLASS,
                ApplyImmediately=True
            )
            message = f"Scaling up DB instance {db_instance_id} from {current_instance_class} to {ORIGINAL_INSTANCE_CLASS} due to high I/O utilization"
            logger.info(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('DB instance scaling initiated')
            }
        except Exception as e:
            logger.error(f"Error scaling up DB instance: {str(e)}")
    
    # If we can't scale up or there was an error, try a reboot
    try:
        rds_client.reboot_db_instance(
            DBInstanceIdentifier=db_instance_id,
            ForceFailover=False
        )
        message = f"Rebooted DB instance {db_instance_id} due to high I/O utilization"
        logger.info(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('DB instance reboot initiated')
        }
    except Exception as e:
        logger.error(f"Error rebooting DB instance: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to heal DB instance')
        }

def verify_backups(instance_details):
    """
    Verify that backups for the RDS instance are working correctly.
    """
    if not BACKUP_VERIFICATION:
        logger.info("Backup verification is disabled")
        return {
            'statusCode': 200,
            'body': json.dumps('Backup verification is disabled')
        }
    
    db_instance_id = instance_details['DBInstanceIdentifier']
    logger.info(f"Verifying backups for DB instance {db_instance_id}")
    
    try:
        # Check if automated backups are enabled
        if not instance_details.get('BackupRetentionPeriod', 0) > 0:
            message = f"Automated backups are not enabled for DB instance {db_instance_id}"
            logger.warning(message)
            send_notification(message)
            return {
                'statusCode': 200,
                'body': json.dumps('Automated backups not enabled')
            }
        
        # Get the latest automated snapshot
        response = rds_client.describe_db_snapshots(
            DBInstanceIdentifier=db_instance_id,
            SnapshotType='automated'
        )
        
        if not response.get('DBSnapshots'):
            message = f"No automated snapshots found for DB instance {db_instance_id}"
            logger.warning(message)
            send_notification(message)
            return {
                'statusCode': 200,
                'body': json.dumps('No automated snapshots found')
            }
        
        # Sort snapshots by creation time (newest first)
        snapshots = sorted(
            response['DBSnapshots'],
            key=lambda x: x.get('SnapshotCreateTime', datetime.min),
            reverse=True
        )
        
        latest_snapshot = snapshots[0]
        snapshot_id = latest_snapshot['DBSnapshotIdentifier']
        snapshot_status = latest_snapshot['Status']
        snapshot_time = latest_snapshot.get('SnapshotCreateTime')
        
        # Check if the latest snapshot is in a valid state
        if snapshot_status != 'available':
            message = f"Latest snapshot {snapshot_id} for DB instance {db_instance_id} is in status {snapshot_status}, not available"
            logger.warning(message)
            send_notification(message)
            return {
                'statusCode': 200,
                'body': json.dumps('Latest snapshot not available')
            }
        
        # Check if the latest snapshot is recent (within the last 24 hours)
        if snapshot_time:
            now = datetime.now().replace(tzinfo=snapshot_time.tzinfo)
            age_hours = (now - snapshot_time).total_seconds() / 3600
            
            if age_hours > 24:
                message = f"Latest snapshot {snapshot_id} for DB instance {db_instance_id} is {age_hours:.1f} hours old"
                logger.warning(message)
                send_notification(message)
                return {
                    'statusCode': 200,
                    'body': json.dumps('Latest snapshot is too old')
                }
        
        message = f"Backup verification successful for DB instance {db_instance_id}. Latest snapshot {snapshot_id} is available."
        logger.info(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('Backup verification successful')
        }
    except Exception as e:
        error_message = f"Error verifying backups for DB instance {db_instance_id}: {str(e)}"
        logger.error(error_message)
        send_notification(error_message)
        
        return {
            'statusCode': 500,
            'body': json.dumps('Backup verification failed')
        }

def handle_config_drift(instance_details, healing_attempts):
    """
    Handle a configuration drift check event.
    """
    db_instance_id = instance_details['DBInstanceIdentifier']
    db_instance_status = instance_details['DBInstanceStatus']
    
    logger.info(f"Checking configuration drift for DB instance {db_instance_id}")
    
    # Check for drift in key attributes
    drift_detected = False
    drift_details = []
    
    # Check instance class drift
    current_instance_class = instance_details['DBInstanceClass']
    if current_instance_class != ORIGINAL_INSTANCE_CLASS:
        drift_detected = True
        drift_details.append(f"Instance class drift detected: current={current_instance_class}, original={ORIGINAL_INSTANCE_CLASS}")
    
    # Check allocated storage drift
    current_allocated_storage = instance_details['AllocatedStorage']
    if current_allocated_storage != ORIGINAL_ALLOCATED_STORAGE:
        drift_detected = True
        drift_details.append(f"Allocated storage drift detected: current={current_allocated_storage}, original={ORIGINAL_ALLOCATED_STORAGE}")
    
    # Check engine version drift
    current_engine_version = instance_details['EngineVersion']
    if current_engine_version != ORIGINAL_ENGINE_VERSION:
        drift_detected = True
        drift_details.append(f"Engine version drift detected: current={current_engine_version}, original={ORIGINAL_ENGINE_VERSION}")
    
    if not drift_detected:
        return {
            'statusCode': 200,
            'body': json.dumps('No configuration drift detected')
        }
    
    # Drift detected, increment healing attempts
    increment_healing_attempts(instance_details['DBInstanceArn'], healing_attempts)
    
    # Log and notify about drift
    drift_message = f"Configuration drift detected for DB instance {db_instance_id}:\n" + "\n".join(drift_details)
    logger.info(drift_message)
    send_notification(drift_message)
    
    # Apply healing actions based on the type of drift
    healing_actions = []
    
    # Only attempt to fix drift if the instance is available
    if db_instance_status != 'available':
        message = f"DB instance {db_instance_id} is in status {db_instance_status}, cannot fix configuration drift"
        logger.info(message)
        send_notification(message)
        return {
            'statusCode': 200,
            'body': json.dumps('Cannot fix configuration drift due to instance status')
        }
    
    # Fix instance class drift if detected
    if current_instance_class != ORIGINAL_INSTANCE_CLASS:
        try:
            rds_client.modify_db_instance(
                DBInstanceIdentifier=db_instance_id,
                DBInstanceClass=ORIGINAL_INSTANCE_CLASS,
                ApplyImmediately=True
            )
            healing_actions.append(f"Changed instance class from {current_instance_class} to {ORIGINAL_INSTANCE_CLASS}")
        except Exception as e:
            error_message = f"Error fixing instance class drift: {str(e)}"
            logger.error(error_message)
            healing_actions.append(error_message)
    
    # Fix allocated storage drift if detected
    if current_allocated_storage != ORIGINAL_ALLOCATED_STORAGE and current_allocated_storage < ORIGINAL_ALLOCATED_STORAGE:
        try:
            rds_client.modify_db_instance(
                DBInstanceIdentifier=db_instance_id,
                AllocatedStorage=ORIGINAL_ALLOCATED_STORAGE,
                ApplyImmediately=True
            )
            healing_actions.append(f"Changed allocated storage from {current_allocated_storage} to {ORIGINAL_ALLOCATED_STORAGE}")
        except Exception as e:
            error_message = f"Error fixing allocated storage drift: {str(e)}"
            logger.error(error_message)
            healing_actions.append(error_message)
    
    # Engine version drift is more complex and might require a snapshot restore
    # For this example, we'll just log it
    if current_engine_version != ORIGINAL_ENGINE_VERSION:
        healing_actions.append(f"Engine version drift detected but not automatically fixed. Manual intervention required.")
    
    # Send notification about healing actions
    healing_message = f"Healing actions for DB instance {db_instance_id}:\n" + "\n".join(healing_actions)
    logger.info(healing_message)
    send_notification(healing_message)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Healing actions applied for configuration drift')
    }

def is_instance_class_larger(class1, class2):
    """
    Compare two instance classes to determine if class1 is larger than class2.
    This is a simplified comparison and might need to be enhanced for all instance types.
    """
    # Extract the instance family and size
    # Example: db.t3.micro -> family=t3, size=micro
    parts1 = class1.split('.')
    parts2 = class2.split('.')
    
    if len(parts1) < 3 or len(parts2) < 3:
        return False
    
    family1 = parts1[1]
    size1 = parts1[2]
    
    family2 = parts2[1]
    size2 = parts2[2]
    
    # Compare families (t < m < r < x)
    family_order = {'t': 1, 'm': 2, 'r': 3, 'x': 4}
    if family1 in family_order and family2 in family_order:
        if family_order[family1] > family_order[family2]:
            return True
        elif family_order[family1] < family_order[family2]:
            return False
    
    # If families are the same, compare sizes
    size_order = {'nano': 1, 'micro': 2, 'small': 3, 'medium': 4, 'large': 5, 'xlarge': 6, '2xlarge': 7, '4xlarge': 8, '8xlarge': 9, '16xlarge': 10}
    if size1 in size_order and size2 in size_order:
        return size_order[size1] > size_order[size2]
    
    # If size has a number prefix (like 2xlarge)
    if size1.endswith('xlarge') and size2.endswith('xlarge'):
        try:
            size1_num = int(size1.replace('xlarge', '')) if size1 != 'xlarge' else 1
            size2_num = int(size2.replace('xlarge', '')) if size2 != 'xlarge' else 1
            return size1_num > size2_num
        except ValueError:
            pass
    
    # Default to false if we can't determine
    return False

def send_notification(message):
    """
    Send an SNS notification if a topic ARN is configured.
    """
    if not SNS_TOPIC_ARN:
        return
    
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"""
==========================================================
RDS SELF-HEALING NOTIFICATION - {timestamp}
==========================================================
DB Instance ID: {DB_INSTANCE_ID}
----------------------------------------------------------
{message}
==========================================================
        """
        
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"RDS Self-Healing Notification - Instance {DB_INSTANCE_ID}",
            Message=formatted_message
        )
    except Exception as e:
        logger.error(f"Error sending SNS notification: {str(e)}")
