import boto3
import os
import json
import base64
import time
from datetime import datetime

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

def lambda_handler(event, context):
    """
    Main handler for EC2 self-healing Lambda function.
    Handles both status check failures and configuration drift.
    """
    print(f"Received event: {json.dumps(event)}")
    
    # Determine the type of event (status check failure or scheduled drift check)
    event_type = determine_event_type(event)
    
    # Get current instance details
    instance_details = get_instance_details(INSTANCE_ID)
    if not instance_details:
        send_notification(f"Unable to retrieve details for instance {INSTANCE_ID}")
        return {
            'statusCode': 500,
            'body': json.dumps('Failed to retrieve instance details')
        }
    
    # Check healing attempts to avoid infinite loops
    healing_attempts = get_healing_attempts(instance_details)
    if healing_attempts >= MAX_HEALING_ATTEMPTS:
        send_notification(f"Maximum healing attempts ({MAX_HEALING_ATTEMPTS}) reached for instance {INSTANCE_ID}")
        return {
            'statusCode': 429,
            'body': json.dumps('Maximum healing attempts reached')
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
        print(f"Error getting instance details: {str(e)}")
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
                }
            ]
        )
        return True
    except Exception as e:
        print(f"Error incrementing healing attempts: {str(e)}")
        return False

def handle_status_check_failure(instance_details, healing_attempts):
    """
    Handle a status check failure event.
    """
    instance_id = instance_details['InstanceId']
    instance_state = instance_details['State']['Name']
    
    print(f"Handling status check failure for instance {instance_id} in state {instance_state}")
    
    # Increment healing attempts
    increment_healing_attempts(instance_id, healing_attempts)
    
    # Apply healing action based on instance state
    if instance_state == 'running':
        try:
            # Try rebooting the instance first
            ec2_client.reboot_instances(InstanceIds=[instance_id])
            message = f"Rebooted instance {instance_id} due to status check failure"
            print(message)
            send_notification(message)
            
            # Wait for the instance to start rebooting
            time.sleep(5)
            
            return {
                'statusCode': 200,
                'body': json.dumps('Instance reboot initiated')
            }
        except Exception as e:
            print(f"Error rebooting instance: {str(e)}")
            
            # If reboot fails, try stopping and starting the instance
            try:
                ec2_client.stop_instances(InstanceIds=[instance_id])
                message = f"Stopping instance {instance_id} due to failed reboot attempt"
                print(message)
                send_notification(message)
                
                return {
                    'statusCode': 200,
                    'body': json.dumps('Instance stop initiated')
                }
            except Exception as e2:
                print(f"Error stopping instance: {str(e2)}")
                return {
                    'statusCode': 500,
                    'body': json.dumps('Failed to heal instance')
                }
    
    elif instance_state == 'stopped':
        try:
            # Start the stopped instance
            ec2_client.start_instances(InstanceIds=[instance_id])
            message = f"Started instance {instance_id} which was in stopped state"
            print(message)
            send_notification(message)
            
            return {
                'statusCode': 200,
                'body': json.dumps('Instance start initiated')
            }
        except Exception as e:
            print(f"Error starting instance: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to start instance')
            }
    
    else:
        message = f"Instance {instance_id} is in state {instance_state}, no healing action taken"
        print(message)
        send_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps('No healing action taken')
        }

def handle_config_drift(instance_details, healing_attempts):
    """
    Handle a configuration drift check event.
    """
    instance_id = instance_details['InstanceId']
    instance_state = instance_details['State']['Name']
    
    print(f"Checking configuration drift for instance {instance_id}")
    
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
    
    # Check security groups drift (can be added based on requirements)
    # Check user data drift (can be added based on requirements)
    
    if not drift_detected:
        return {
            'statusCode': 200,
            'body': json.dumps('No configuration drift detected')
        }
    
    # Drift detected, increment healing attempts
    increment_healing_attempts(instance_id, healing_attempts)
    
    # Log and notify about drift
    drift_message = f"Configuration drift detected for instance {instance_id}:\n" + "\n".join(drift_details)
    print(drift_message)
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
                # In a real implementation, you might want to use a Step Function or another Lambda
                # for this part of the workflow instead of waiting in the Lambda
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
                print(error_message)
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
                print(error_message)
                healing_actions.append(error_message)
    
    # AMI drift is more complex and might require a new instance
    # For this example, we'll just log it
    if current_ami != ORIGINAL_AMI:
        healing_actions.append(f"AMI drift detected but not automatically fixed. Manual intervention required.")
    
    # Send notification about healing actions
    healing_message = f"Healing actions for instance {instance_id}:\n" + "\n".join(healing_actions)
    print(healing_message)
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
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"EC2 Self-Healing Notification - Instance {INSTANCE_ID}",
            Message=message
        )
    except Exception as e:
        print(f"Error sending SNS notification: {str(e)}")
