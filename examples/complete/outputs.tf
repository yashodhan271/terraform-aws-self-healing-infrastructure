output "instance_id" {
  description = "ID of the self-healing EC2 instance"
  value       = module.self_healing_ec2.instance_id
}

output "instance_public_ip" {
  description = "Public IP address of the self-healing EC2 instance"
  value       = module.self_healing_ec2.public_ip
}

output "lambda_function_name" {
  description = "Name of the Lambda function responsible for healing"
  value       = module.self_healing_ec2.lambda_function_name
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic for healing notifications"
  value       = aws_sns_topic.healing_notifications.arn
}

output "cloudwatch_dashboard_url" {
  description = "URL to the CloudWatch dashboard for monitoring the self-healing infrastructure"
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.self_healing_dashboard.dashboard_name}"
}

output "vpc_id" {
  description = "ID of the VPC where resources are deployed"
  value       = module.vpc.vpc_id
}

output "security_group_id" {
  description = "ID of the security group attached to the EC2 instance"
  value       = aws_security_group.instance_sg.id
}
