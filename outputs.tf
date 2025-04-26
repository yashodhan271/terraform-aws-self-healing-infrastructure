output "sns_topic_arn" {
  description = "ARN of the SNS topic for healing notifications"
  value       = var.enable_notifications ? aws_sns_topic.healing_notifications[0].arn : null
}

output "dashboard_name" {
  description = "Name of the CloudWatch dashboard for monitoring self-healing metrics"
  value       = var.create_dashboard ? aws_cloudwatch_dashboard.self_healing_dashboard[0].dashboard_name : null
}

output "module_version" {
  description = "Version of the self-healing infrastructure module"
  value       = "1.0.0"
}
