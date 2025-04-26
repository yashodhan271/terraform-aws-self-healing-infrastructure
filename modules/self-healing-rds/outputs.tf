output "db_instance_id" {
  description = "ID of the RDS instance"
  value       = aws_db_instance.self_healing.id
}

output "db_instance_arn" {
  description = "ARN of the RDS instance"
  value       = aws_db_instance.self_healing.arn
}

output "db_instance_endpoint" {
  description = "Endpoint of the RDS instance"
  value       = aws_db_instance.self_healing.endpoint
}

output "db_instance_address" {
  description = "Address of the RDS instance"
  value       = aws_db_instance.self_healing.address
}

output "db_instance_port" {
  description = "Port of the RDS instance"
  value       = aws_db_instance.self_healing.port
}

output "db_subnet_group_name" {
  description = "Name of the DB subnet group"
  value       = aws_db_subnet_group.self_healing.name
}

output "lambda_function_name" {
  description = "Name of the Lambda function responsible for healing"
  value       = aws_lambda_function.rds_healing.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function responsible for healing"
  value       = aws_lambda_function.rds_healing.arn
}

output "cloudwatch_alarm_names" {
  description = "Names of the CloudWatch alarms monitoring the instance"
  value = [
    aws_cloudwatch_metric_alarm.cpu_utilization.alarm_name,
    aws_cloudwatch_metric_alarm.free_storage_space.alarm_name,
    aws_cloudwatch_metric_alarm.database_connections.alarm_name
  ]
}

output "event_rule_names" {
  description = "Names of the EventBridge rules for self-healing"
  value = [
    aws_cloudwatch_event_rule.performance_issue.name,
    aws_cloudwatch_event_rule.config_drift_check.name
  ]
}
