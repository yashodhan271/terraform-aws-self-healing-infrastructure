import boto3
import os
import json
import base64
import time
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
ec2_client = boto3.client('ec2')
cloudwatch_client = boto3.client('cloudwatch')
sns_client = boto3.client('sns')

# Get environment variables
INSTANCE_ID = os.environ.get('INSTANCE_ID')
MAX_HEALING_ATTEMPTS = int(os.environ.get('MAX_HEALING_ATTEMPTS', 3))
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
ORIGINAL_AMI = os.environ.get('ORIGINAL_AMI')
ORIGINAL_INSTANCE_TYPE = os.environ.get('ORIGINAL_INSTANCE_TYPE')
ORIGINAL_USER_DATA = os.environ.get('ORIGINAL_USER_DATA', '')
ORIGINAL_SECURITY_GROUPS = os.environ.get('ORIGINAL_SECURITY_GROUPS', '').split(',')
CUSTOM_HEALING_ACTIONS = os.environ.get('CUSTOM_HEALING_ACTIONS', 'default')

# Constants
TRANSITIONAL_STATES = ['pending', 'stopping', 'shutting-down']
RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds

def lambda_handler(event, context):
    """
    Main handler for EC2 self-healing Lambda function.
    Handles both status check failures and configuration drift.
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Determine the type of event (status check failure or scheduled drift check)
    event_type = determine_event_type(event)
    
    # Get current instance details with retry logic for transient failures
    instance_details = get_instance_details_with_retry(INSTANCE_ID)
    if not instance_details:
        message = f"Unable to retrieve details for instance {INSTANCE_ID} after multiple attempts"
        logger.error(message)
        send_notification(message)
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to retrieve instance details')
        }
    
    # Check healing attempts to avoid infinite loops
    healing_attempts = get_healing_attempts(instance_details)
    if healing_attempts >= MAX_HEALING_ATTEMPTS:
        message = f"Maximum healing attempts ({MAX_HEALING_ATTEMPTS}) reached for instance {INSTANCE_ID}"
        logger.warning(message)
        send_notification(message)
        return {
            'statusCode': 429,
            'body': json.dumps('Maximum healing attempts reached')
        }
    
    # Check if instance is in a transitional state
    instance_state = instance_details['State']['Name']
    if instance_state in TRANSITIONAL_STATES:
        message = f"Instance {INSTANCE_ID} is in transitional state {instance_state}. Healing deferred."
        logger.info(message)
        send_notification(message)
        return {
            'statusCode': 202,
            'body': json.dumps('Healing deferred due to transitional state')
        }
    
    # Handle the event based on its type
    if event_type == 'status_check_failure':
        result = handle_status_check_failure(instance_details, healing_attempts)
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
    Determine whether this is a status check failure or a scheduled drift check.
    """
    # Check if this is a CloudWatch alarm event (status check failure)
    if 'detail-type' in event and event['detail-type'] == 'CloudWatch Alarm State Change':
        return 'status_check_failure'
    
    # Otherwise, assume it's a scheduled drift check
    return 'config_drift'

def get_instance_details_with_retry(instance_id, max_retries=RETRY_COUNT):
    """
    Get details about the EC2 instance with retry logic for transient failures.
    """
    retries = 0
    while retries < max_retries:
        try:
            response = ec2_client.describe_instances(InstanceIds=[instance_id])
            if response['Reservations'] and response['Reservations'][0]['Instances']:
                return response['Reservations'][0]['Instances'][0]
            return None
        except Exception as e:
            logger.warning(f"Error getting instance details (attempt {retries+1}/{max_retries}): {str(e)}")
            retries += 1
            if retries < max_retries:
                time.sleep(RETRY_DELAY)
    
    logger.error(f"Failed to get instance details after {max_retries} attempts")
    return None

def get_instance_details(instance_id):
    """
    Get details about the EC2 instance.
    """
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        if response['Reservations'] and response['Reservations'][0]['Instances']:
            return response['Reservations'][0]['Instances'][0]
        return None
    except Exception as e:
        logger.error(f"Error getting instance details: {str(e)}")
        return None

def get_healing_attempts(instance_details):
    """
    Get the number of healing attempts from instance tags.
    """
    if 'Tags' not in instance_details:
        return 0
    
    for tag in instance_details['Tags']:
        if tag['Key'] == 'HealingAttempts':
            try:
                return int(tag['Value'])
            except ValueError:
                return 0
    
    return 0

def increment_healing_attempts(instance_id, current_attempts):
    """
    Increment the healing attempts counter in instance tags.
    """
    try:
        ec2_client.create_tags(
            Resources=[instance_id],
            Tags=[
                {
                    'Key': 'HealingAttempts',
                    'Value': str(current_attempts + 1)
                },
                {
                    'Key': 'LastHealed',
                    'Value': datetime.now().isoformat()
                },
                {
                    'Key': 'LastHealingAction',
                    'Value': datetime.now().isoformat()
                }
            ]
        )
        return True
    except Exception as e:
        logger.error(f"Error incrementing healing attempts: {str(e)}")
        return False

def handle_status_check_failure(instance_details, healing_attempts):
    """
    Handle a status check failure event.
    """
    instance_id = instance_details['InstanceId']
    instance_state = instance_details['State']['Name']
    
    logger.info(f"Handling status check failure for instance {instance_id} in state {instance_state}")
    
    # Increment healing attempts
    increment_healing_attempts(instance_id, healing_attempts)
    
    # Apply healing action based on instance state
    if instance_state == 'running':
        # Check if custom healing actions are specified
        if CUSTOM_HEALING_ACTIONS != 'default':
            return apply_custom_healing_action(instance_id, CUSTOM_HEALING_ACTIONS)
        
        try:
            # Try rebooting the instance first
            ec2_client.reboot_instances(InstanceIds=[instance_id])
            message = f"Rebooted instance {instance_id} due to status check failure"
            logger.info(message)
            send_notification(message)
            
            # Wait for the instance to start rebooting
            time.sleep(5)
            
            return {
                'statusCode': 200,
                'body': json.dumps('Instance reboot initiated')
            }
        except Exception as e:
            logger.error(f"Error rebooting instance: {str(e)}")
            
            # If reboot fails, try stopping and starting the instance
            try:
                ec2_client.stop_instances(InstanceIds=[instance_id])
                message = f"Stopping instance {instance_id} due to failed reboot attempt"
                logger.info(message)
                send_notification(message)
                
                return {
                    'statusCode': 200,
                    'body': json.dumps('Instance stop initiated')
                }
            except Exception as e2:
                logger.error(f"Error stopping instance: {str(e2)}")
                return {
                    'statusCode': 500,
                    'body': json.dumps('Failed to heal instance')
                }
    
    elif instance_state == 'stopped':
        try:
            # Start the stopped instance
            ec2_client.start_instances(InstanceIds=[instance_id])
            message = f"Started instance {instance_id} which was in stopped state"
            logger.info(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('Instance start initiated')
            }
        except Exception as e:
            logger.error(f"Error starting instance: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to start instance')
            }
    
    else:
        message = f"Instance {instance_id} is in state {instance_state}, no healing action taken"
        logger.info(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('No healing action taken')
        }

def apply_custom_healing_action(instance_id, action_type):
    """
    Apply custom healing actions defined in environment variables.
    """
    logger.info(f"Applying custom healing action: {action_type}")
    
    if action_type == 'stop_start':
        try:
            ec2_client.stop_instances(InstanceIds=[instance_id])
            message = f"Custom healing: Stopping instance {instance_id} for stop-start cycle"
            logger.info(message)
            send_notification(message)
            
            # Wait for the instance to stop
            waiter = ec2_client.get_waiter('instance_stopped')
            waiter.wait(InstanceIds=[instance_id])
            
            # Start the instance
            ec2_client.start_instances(InstanceIds=[instance_id])
            message = f"Custom healing: Starting instance {instance_id} after stop"
            logger.info(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('Custom healing action (stop-start) completed')
            }
        except Exception as e:
            logger.error(f"Error in custom healing action: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to apply custom healing action')
            }
    
    elif action_type == 'restore_from_backup':
        # This would implement logic to restore from a backup or snapshot
        # Placeholder for future implementation
        message = f"Custom healing action 'restore_from_backup' not yet implemented"
        logger.warning(message)
        send_notification(message)
        
        return {
            'statusCode': 501,
            'body': json.dumps('Custom healing action not implemented')
        }
    
    else:
        # Default to reboot if custom action is not recognized
        try:
            ec2_client.reboot_instances(InstanceIds=[instance_id])
            message = f"Custom healing: Rebooted instance {instance_id} (unknown action type '{action_type}')"
            logger.info(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('Default reboot healing action applied')
            }
        except Exception as e:
            logger.error(f"Error in default healing action: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to apply default healing action')
            }

def handle_config_drift(instance_details, healing_attempts):
    """
    Handle a configuration drift check event.
    """
    instance_id = instance_details['InstanceId']
    instance_state = instance_details['State']['Name']
    
    logger.info(f"Checking configuration drift for instance {instance_id}")
    
    # Check for drift in key attributes
    drift_detected = False
    drift_details = []
    
    # Check AMI drift
    current_ami = instance_details['ImageId']
    if current_ami != ORIGINAL_AMI:
        drift_detected = True
        drift_details.append(f"AMI drift detected: current={current_ami}, original={ORIGINAL_AMI}")
    
    # Check instance type drift
    current_instance_type = instance_details['InstanceType']
    if current_instance_type != ORIGINAL_INSTANCE_TYPE:
        drift_detected = True
        drift_details.append(f"Instance type drift detected: current={current_instance_type}, original={ORIGINAL_INSTANCE_TYPE}")
    
    # Check security groups drift
    if ORIGINAL_SECURITY_GROUPS and ORIGINAL_SECURITY_GROUPS[0]:  # Check if we have original security groups defined
        current_sg_ids = [sg['GroupId'] for sg in instance_details.get('SecurityGroups', [])]
        if set(current_sg_ids) != set(ORIGINAL_SECURITY_GROUPS):
            drift_detected = True
            drift_details.append(f"Security groups drift detected: current={current_sg_ids}, original={ORIGINAL_SECURITY_GROUPS}")
    
    # Check for maintenance window tags to avoid healing during planned maintenance
    in_maintenance = False
    if 'Tags' in instance_details:
        for tag in instance_details['Tags']:
            if tag['Key'] == 'MaintenanceWindow' and tag['Value'].lower() == 'active':
                in_maintenance = True
                logger.info(f"Instance {instance_id} is in maintenance window, skipping drift remediation")
                break
    
    if not drift_detected:
        return {
            'statusCode': 200,
            'body': json.dumps('No configuration drift detected')
        }
    
    # Drift detected, but skip remediation if in maintenance window
    if in_maintenance:
        message = f"Configuration drift detected for instance {instance_id}, but instance is in maintenance window. Skipping remediation."
        logger.info(message)
        send_notification(message)
        return {
            'statusCode': 200,
            'body': json.dumps('Drift remediation skipped due to maintenance window')
        }
    
    # Drift detected, increment healing attempts
    increment_healing_attempts(instance_id, healing_attempts)
    
    # Log and notify about drift
    drift_message = f"Configuration drift detected for instance {instance_id}:\n" + "\n".join(drift_details)
    logger.info(drift_message)
    send_notification(drift_message)
    
    # Apply healing actions based on the type of drift
    healing_actions = []
    
    # Fix instance type drift if detected
    if current_instance_type != ORIGINAL_INSTANCE_TYPE:
        if instance_state == 'running':
            try:
                # Need to stop the instance to change instance type
                ec2_client.stop_instances(InstanceIds=[instance_id])
                healing_actions.append(f"Stopping instance to fix instance type drift")
                
                # Wait for the instance to stop before changing type
                waiter = ec2_client.get_waiter('instance_stopped')
                waiter.wait(InstanceIds=[instance_id])
                
                # Change instance type
                ec2_client.modify_instance_attribute(
                    InstanceId=instance_id,
                    InstanceType={'Value': ORIGINAL_INSTANCE_TYPE}
                )
                healing_actions.append(f"Changed instance type from {current_instance_type} to {ORIGINAL_INSTANCE_TYPE}")
                
                # Start the instance again
                ec2_client.start_instances(InstanceIds=[instance_id])
                healing_actions.append(f"Started instance after fixing instance type")
            except Exception as e:
                error_message = f"Error fixing instance type drift: {str(e)}"
                logger.error(error_message)
                healing_actions.append(error_message)
        else:
            try:
                # Instance is already stopped, just change the type
                ec2_client.modify_instance_attribute(
                    InstanceId=instance_id,
                    InstanceType={'Value': ORIGINAL_INSTANCE_TYPE}
                )
                healing_actions.append(f"Changed instance type from {current_instance_type} to {ORIGINAL_INSTANCE_TYPE}")
                
                # Start the instance if it was stopped
                if instance_state == 'stopped':
                    ec2_client.start_instances(InstanceIds=[instance_id])
                    healing_actions.append(f"Started instance after fixing instance type")
            except Exception as e:
                error_message = f"Error fixing instance type drift: {str(e)}"
                logger.error(error_message)
                healing_actions.append(error_message)
    
    # Fix security groups drift if detected
    if ORIGINAL_SECURITY_GROUPS and ORIGINAL_SECURITY_GROUPS[0]:
        current_sg_ids = [sg['GroupId'] for sg in instance_details.get('SecurityGroups', [])]
        if set(current_sg_ids) != set(ORIGINAL_SECURITY_GROUPS):
            try:
                # Modify security groups
                ec2_client.modify_instance_attribute(
                    InstanceId=instance_id,
                    Groups=ORIGINAL_SECURITY_GROUPS
                )
                healing_actions.append(f"Restored security groups from {current_sg_ids} to {ORIGINAL_SECURITY_GROUPS}")
            except Exception as e:
                error_message = f"Error fixing security groups drift: {str(e)}"
                logger.error(error_message)
                healing_actions.append(error_message)
    
    # AMI drift is more complex and might require a new instance
    # For this example, we'll just log it
    if current_ami != ORIGINAL_AMI:
        healing_actions.append(f"AMI drift detected but not automatically fixed. Manual intervention required.")
    
    # Send notification about healing actions
    healing_message = f"Healing actions for instance {instance_id}:\n" + "\n".join(healing_actions)
    logger.info(healing_message)
    send_notification(healing_message)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Healing actions applied for configuration drift')
    }

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
SELF-HEALING NOTIFICATION - {timestamp}
==========================================================
Instance ID: {INSTANCE_ID}
----------------------------------------------------------
{message}
==========================================================
        """
        
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"EC2 Self-Healing Notification - Instance {INSTANCE_ID}",
            Message=formatted_message
        )
    except Exception as e:
        logger.error(f"Error sending SNS notification: {str(e)}")
