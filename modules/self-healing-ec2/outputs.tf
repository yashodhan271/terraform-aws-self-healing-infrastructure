output "instance_id" {
  description = "ID of the EC2 instance"
  value       = aws_instance.self_healing.id
}

output "instance_arn" {
  description = "ARN of the EC2 instance"
  value       = aws_instance.self_healing.arn
}

output "private_ip" {
  description = "Private IP address of the EC2 instance"
  value       = aws_instance.self_healing.private_ip
}

output "public_ip" {
  description = "Public IP address of the EC2 instance, if applicable"
  value       = aws_instance.self_healing.public_ip
}

output "lambda_function_name" {
  description = "Name of the Lambda function responsible for healing"
  value       = aws_lambda_function.ec2_healing.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function responsible for healing"
  value       = aws_lambda_function.ec2_healing.arn
}

output "cloudwatch_alarm_name" {
  description = "Name of the CloudWatch alarm monitoring the instance"
  value       = aws_cloudwatch_metric_alarm.status_check_failed.alarm_name
}

output "cloudwatch_alarm_arn" {
  description = "ARN of the CloudWatch alarm monitoring the instance"
  value       = aws_cloudwatch_metric_alarm.status_check_failed.arn
}

output "event_rule_names" {
  description = "Names of the EventBridge rules for self-healing"
  value = [
    aws_cloudwatch_event_rule.status_check_failed.name,
    aws_cloudwatch_event_rule.config_drift_check.name
  ]
}
