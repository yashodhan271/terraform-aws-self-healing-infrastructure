# Self-Healing Infrastructure Monitoring Module

This module provides centralized monitoring capabilities for the self-healing infrastructure. It sets up CloudWatch dashboards, alarms, and EventBridge rules to detect issues across all infrastructure components and trigger appropriate healing actions.

## Features

- **Unified Monitoring Dashboard**: Single pane of glass for all self-healing infrastructure components
- **Cross-Resource Correlation**: Correlate events and metrics across different resource types
- **Customizable Alarm Thresholds**: Define thresholds for different environments (dev, staging, production)
- **Healing Event Tracking**: Track all self-healing events and their outcomes
- **Notification Management**: Centralized management of healing notifications

## Usage

```hcl
module "monitoring" {
  source = "../../modules/monitoring"

  name_prefix        = "production"
  region             = "us-east-1"
  
  # Resources to monitor
  ec2_instances      = [module.self_healing_ec2.instance_id]
  rds_instances      = [module.self_healing_rds.db_instance_id]
  
  # Notification settings
  sns_topic_arn      = aws_sns_topic.healing_notifications.arn
  notification_email = "admin@example.com"
  
  # Alarm thresholds
  cpu_threshold      = 80
  memory_threshold   = 80
  disk_threshold     = 85
  
  # Dashboard settings
  create_dashboard   = true
  
  tags = {
    Environment = "production"
    Managed     = "terraform"
  }
}
```

## How It Works

1. **Resource Registration**: Register resources to be monitored (EC2 instances, RDS databases, etc.)
2. **Metric Collection**: CloudWatch collects metrics from all registered resources
3. **Alarm Configuration**: Alarms are configured based on specified thresholds
4. **Event Correlation**: EventBridge rules correlate events across resources
5. **Dashboard Creation**: A unified dashboard displays the health and healing status of all resources
6. **Notification Management**: Notifications are sent through a centralized SNS topic

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.0.0 |
| aws | >= 4.0.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| name_prefix | Prefix to be used for naming resources | `string` | `"self-healing"` | no |
| region | AWS region where resources are deployed | `string` | `"us-east-1"` | no |
| ec2_instances | List of EC2 instance IDs to monitor | `list(string)` | `[]` | no |
| rds_instances | List of RDS instance IDs to monitor | `list(string)` | `[]` | no |
| sns_topic_arn | ARN of the SNS topic for healing notifications | `string` | `""` | no |
| notification_email | Email address to receive healing notifications | `string` | `""` | no |
| cpu_threshold | CPU utilization threshold percentage for alarms | `number` | `80` | no |
| memory_threshold | Memory utilization threshold percentage for alarms | `number` | `80` | no |
| disk_threshold | Disk utilization threshold percentage for alarms | `number` | `85` | no |
| create_dashboard | Whether to create a CloudWatch dashboard | `bool` | `true` | no |
| dashboard_refresh_interval | Dashboard refresh interval in seconds | `number` | `300` | no |
| tags | Tags to apply to all resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| dashboard_name | Name of the CloudWatch dashboard |
| dashboard_url | URL to the CloudWatch dashboard |
| sns_topic_arn | ARN of the SNS topic for healing notifications |
| alarm_arns | ARNs of the CloudWatch alarms |
| event_rule_arns | ARNs of the EventBridge rules |
