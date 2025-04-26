# Self-Healing RDS Module

This module provisions an Amazon RDS database instance with self-healing capabilities. It automatically detects and recovers from database failures, configuration drift, and performance issues.

## Features

- **Automatic Failure Detection**: Monitors RDS health metrics and automatically initiates recovery actions
- **Configuration Drift Detection**: Periodically checks for unauthorized configuration changes and reverts them
- **Performance Monitoring**: Tracks key performance metrics and takes corrective actions when thresholds are exceeded
- **Automated Backup Verification**: Regularly verifies database backups to ensure recoverability
- **Self-Healing Lambda Function**: Executes recovery actions when issues are detected

## Usage

```hcl
module "self_healing_rds" {
  source = "../../modules/self-healing-rds"

  name_prefix           = "example"
  instance_identifier   = "example-db"
  engine                = "mysql"
  engine_version        = "8.0"
  instance_class        = "db.t3.micro"
  allocated_storage     = 20
  storage_type          = "gp2"
  username              = "admin"
  password              = var.db_password
  vpc_security_group_ids = [aws_security_group.db_sg.id]
  subnet_ids            = module.vpc.database_subnets
  
  backup_retention_period = 7
  backup_window           = "03:00-05:00"
  maintenance_window      = "Mon:00:00-Mon:03:00"
  
  drift_check_interval   = 15
  max_healing_attempts   = 3
  sns_topic_arn          = aws_sns_topic.healing_notifications.arn
  
  tags = {
    Environment = "production"
    Managed     = "terraform"
  }
}
```

## How It Works

1. **Monitoring**: CloudWatch alarms continuously monitor the RDS instance for failures and performance issues
2. **Drift Detection**: A Lambda function periodically checks the instance configuration against the expected state
3. **Automated Recovery**: When issues are detected, the Lambda function initiates appropriate recovery actions:
   - Rebooting the instance for minor issues
   - Restoring from snapshot for data corruption
   - Reverting configuration changes for drift
4. **Notifications**: All healing actions trigger SNS notifications for visibility

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.0.0 |
| aws | >= 4.0.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| name_prefix | Prefix to be used for naming resources | `string` | `"self-healing"` | no |
| instance_identifier | Identifier for the RDS instance | `string` | n/a | yes |
| engine | Database engine type | `string` | n/a | yes |
| engine_version | Database engine version | `string` | n/a | yes |
| instance_class | Instance class for the RDS instance | `string` | n/a | yes |
| allocated_storage | Allocated storage in GB | `number` | `20` | yes |
| storage_type | Storage type for the RDS instance | `string` | `"gp2"` | no |
| username | Master username for the database | `string` | n/a | yes |
| password | Master password for the database | `string` | n/a | yes |
| vpc_security_group_ids | List of VPC security group IDs | `list(string)` | n/a | yes |
| subnet_ids | List of subnet IDs for the DB subnet group | `list(string)` | n/a | yes |
| backup_retention_period | Number of days to retain backups | `number` | `7` | no |
| backup_window | Daily time range during which backups are created | `string` | `"03:00-05:00"` | no |
| maintenance_window | Weekly time range during which maintenance can occur | `string` | `"Mon:00:00-Mon:03:00"` | no |
| drift_check_interval | Interval in minutes for checking configuration drift | `number` | `15` | no |
| max_healing_attempts | Maximum number of healing attempts before giving up | `number` | `3` | no |
| sns_topic_arn | ARN of the SNS topic for healing notifications | `string` | `""` | no |
| tags | Tags to apply to all resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| db_instance_id | ID of the RDS instance |
| db_instance_arn | ARN of the RDS instance |
| db_instance_endpoint | Endpoint of the RDS instance |
| lambda_function_name | Name of the Lambda function responsible for healing |
| lambda_function_arn | ARN of the Lambda function responsible for healing |
| cloudwatch_alarm_names | Names of the CloudWatch alarms monitoring the instance |
| event_rule_names | Names of the EventBridge rules for self-healing |
