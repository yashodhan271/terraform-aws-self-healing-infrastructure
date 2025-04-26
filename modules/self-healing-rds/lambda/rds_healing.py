import boto3
import os
import json
import time
from datetime import datetime

# Initialize AWS clients
rds_client = boto3.client('rds')
cloudwatch_client = boto3.client('cloudwatch')
sns_client = boto3.client('sns')

# Get environment variables
DB_INSTANCE_ID = os.environ.get('DB_INSTANCE_ID')
MAX_HEALING_ATTEMPTS = int(os.environ.get('MAX_HEALING_ATTEMPTS', 3))
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
ORIGINAL_INSTANCE_CLASS = os.environ.get('ORIGINAL_INSTANCE_CLASS')
ORIGINAL_ALLOCATED_STORAGE = int(os.environ.get('ORIGINAL_ALLOCATED_STORAGE', 0))
ORIGINAL_ENGINE_VERSION = os.environ.get('ORIGINAL_ENGINE_VERSION')

def lambda_handler(event, context):
    """
    Main handler for RDS self-healing Lambda function.
    Handles both performance issues and configuration drift.
    """
    print(f"Received event: {json.dumps(event)}")
    
    # Determine the type of event (performance issue or scheduled drift check)
    event_type = determine_event_type(event)
    
    # Get current instance details
    instance_details = get_instance_details(DB_INSTANCE_ID)
    if not instance_details:
        send_notification(f"Unable to retrieve details for DB instance {DB_INSTANCE_ID}")
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to retrieve instance details')
        }
    
    # Check healing attempts to avoid infinite loops
    healing_attempts = get_healing_attempts(instance_details)
    if healing_attempts >= MAX_HEALING_ATTEMPTS:
        send_notification(f"Maximum healing attempts ({MAX_HEALING_ATTEMPTS}) reached for DB instance {DB_INSTANCE_ID}")
        return {
            'statusCode': 429,
            'body': json.dumps('Maximum healing attempts reached')
        }
    
    # Handle the event based on its type
    if event_type == 'performance_issue':
        result = handle_performance_issue(instance_details, event, healing_attempts)
    elif event_type == 'config_drift':
        result = handle_config_drift(instance_details, healing_attempts)
    else:
        result = {
            'statusCode': 400,
            'body': json.dumps('Unknown event type')
        }
    
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

def get_instance_details(db_instance_id):
    """
    Get details about the RDS instance.
    """
    try:
        response = rds_client.describe_db_instances(DBInstanceIdentifier=db_instance_id)
        if response['DBInstances']:
            return response['DBInstances'][0]
        return None
    except Exception as e:
        print(f"Error getting instance details: {str(e)}")
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
        print(f"Error getting healing attempts: {str(e)}")
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
        print(f"Error incrementing healing attempts: {str(e)}")
        return False

def handle_performance_issue(instance_details, event, healing_attempts):
    """
    Handle a performance issue event.
    """
    db_instance_id = instance_details['DBInstanceIdentifier']
    db_instance_status = instance_details['DBInstanceStatus']
    
    print(f"Handling performance issue for DB instance {db_instance_id} in status {db_instance_status}")
    
    # Get alarm details to determine the specific issue
    alarm_name = None
    if 'detail' in event and 'alarmName' in event['detail']:
        alarm_name = event['detail']['alarmName']
    
    # Increment healing attempts
    increment_healing_attempts(instance_details['DBInstanceArn'], healing_attempts)
    
    # Apply healing action based on instance status and alarm
    if db_instance_status == 'available':
        # Determine the appropriate action based on the alarm
        if alarm_name and 'cpu-utilization' in alarm_name.lower():
            return handle_cpu_issue(db_instance_id, instance_details)
        elif alarm_name and 'free-storage-space' in alarm_name.lower():
            return handle_storage_issue(db_instance_id, instance_details)
        elif alarm_name and 'database-connections' in alarm_name.lower():
            return handle_connections_issue(db_instance_id, instance_details)
        else:
            # If we can't determine the specific issue, try a reboot
            try:
                rds_client.reboot_db_instance(
                    DBInstanceIdentifier=db_instance_id,
                    ForceFailover=False
                )
                message = f"Rebooted DB instance {db_instance_id} due to performance issue"
                print(message)
                send_notification(message)
                
                return {
                    'statusCode': 200,
                    'body': json.dumps('DB instance reboot initiated')
                }
            except Exception as e:
                print(f"Error rebooting DB instance: {str(e)}")
                return {
                    'statusCode': 500,
                    'body': json.dumps('Failed to heal DB instance')
                }
    else:
        message = f"DB instance {db_instance_id} is in status {db_instance_status}, no healing action taken"
        print(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('No healing action taken')
        }

def handle_cpu_issue(db_instance_id, instance_details):
    """
    Handle high CPU utilization by scaling up the instance if needed.
    """
    current_instance_class = instance_details['DBInstanceClass']
    
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
            print(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('DB instance scaling initiated')
            }
        except Exception as e:
            print(f"Error scaling up DB instance: {str(e)}")
    
    # If we can't scale up or there was an error, try a reboot
    try:
        rds_client.reboot_db_instance(
            DBInstanceIdentifier=db_instance_id,
            ForceFailover=False
        )
        message = f"Rebooted DB instance {db_instance_id} due to high CPU utilization"
        print(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('DB instance reboot initiated')
        }
    except Exception as e:
        print(f"Error rebooting DB instance: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to heal DB instance')
        }

def handle_storage_issue(db_instance_id, instance_details):
    """
    Handle low storage space by increasing allocated storage.
    """
    current_allocated_storage = instance_details['AllocatedStorage']
    
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
            print(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('DB instance storage increase initiated')
            }
        except Exception as e:
            print(f"Error increasing DB instance storage: {str(e)}")
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
            print(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('DB instance storage increase initiated')
            }
        except Exception as e:
            print(f"Error increasing DB instance storage: {str(e)}")
    
    # If we can't increase storage or there was an error, notify
    message = f"Unable to increase storage for DB instance {db_instance_id}. Manual intervention required."
    print(message)
    send_notification(message)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Manual intervention required for storage issue')
    }

def handle_connections_issue(db_instance_id, instance_details):
    """
    Handle high connection count by rebooting the instance.
    """
    try:
        rds_client.reboot_db_instance(
            DBInstanceIdentifier=db_instance_id,
            ForceFailover=False
        )
        message = f"Rebooted DB instance {db_instance_id} due to high connection count"
        print(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('DB instance reboot initiated')
        }
    except Exception as e:
        print(f"Error rebooting DB instance: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to heal DB instance')
        }

def handle_config_drift(instance_details, healing_attempts):
    """
    Handle a configuration drift check event.
    """
    db_instance_id = instance_details['DBInstanceIdentifier']
    db_instance_status = instance_details['DBInstanceStatus']
    
    print(f"Checking configuration drift for DB instance {db_instance_id}")
    
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
    print(drift_message)
    send_notification(drift_message)
    
    # Apply healing actions based on the type of drift
    healing_actions = []
    
    # Only attempt to fix drift if the instance is available
    if db_instance_status != 'available':
        message = f"DB instance {db_instance_id} is in status {db_instance_status}, cannot fix configuration drift"
        print(message)
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
            print(error_message)
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
            print(error_message)
            healing_actions.append(error_message)
    
    # Engine version drift is more complex and might require a snapshot restore
    # For this example, we'll just log it
    if current_engine_version != ORIGINAL_ENGINE_VERSION:
        healing_actions.append(f"Engine version drift detected but not automatically fixed. Manual intervention required.")
    
    # Send notification about healing actions
    healing_message = f"Healing actions for DB instance {db_instance_id}:\n" + "\n".join(healing_actions)
    print(healing_message)
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
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"RDS Self-Healing Notification - Instance {DB_INSTANCE_ID}",
            Message=message
        )
    except Exception as e:
        print(f"Error sending SNS notification: {str(e)}")
