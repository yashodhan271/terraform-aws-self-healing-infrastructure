/**
 * # Self-Healing RDS Module
 *
 * This module deploys an RDS instance with self-healing capabilities.
 * It automatically detects and recovers from database failures and configuration drift.
 */

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.0.0"
    }
  }
}

locals {
  lambda_function_name = "${var.name_prefix}-rds-healing-function"
  event_rule_name      = "${var.name_prefix}-rds-healing-rule"
  alarm_prefix         = "${var.name_prefix}-rds"
  tags = merge(
    var.tags,
    {
      "ManagedBy" = "terraform"
      "Module"    = "self-healing-rds"
    }
  )
}

# RDS Instance
resource "aws_db_instance" "self_healing" {
  identifier           = var.instance_identifier
  engine               = var.engine
  engine_version       = var.engine_version
  instance_class       = var.instance_class
  allocated_storage    = var.allocated_storage
  storage_type         = var.storage_type
  storage_encrypted    = var.storage_encrypted
  
  db_name              = var.db_name
  username             = var.username
  password             = var.password
  
  vpc_security_group_ids = var.vpc_security_group_ids
  db_subnet_group_name   = aws_db_subnet_group.self_healing.name
  parameter_group_name   = var.parameter_group_name
  
  backup_retention_period = var.backup_retention_period
  backup_window           = var.backup_window
  maintenance_window      = var.maintenance_window
  
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.instance_identifier}-final-snapshot"
  
  deletion_protection      = var.deletion_protection
  auto_minor_version_upgrade = var.auto_minor_version_upgrade
  
  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.rds_monitoring_role.arn
  
  # Store the original configuration as tags for drift detection
  tags = merge(
    local.tags,
    {
      "OriginalInstanceClass" = var.instance_class
      "OriginalAllocatedStorage" = var.allocated_storage
      "OriginalEngineVersion" = var.engine_version
    }
  )
  
  lifecycle {
    ignore_changes = [
      tags["LastHealed"],
      tags["HealingAttempts"]
    ]
  }
}

# DB Subnet Group
resource "aws_db_subnet_group" "self_healing" {
  name       = "${var.name_prefix}-subnet-group"
  subnet_ids = var.subnet_ids
  tags       = local.tags
}

# CloudWatch Alarms for RDS Monitoring
resource "aws_cloudwatch_metric_alarm" "cpu_utilization" {
  alarm_name          = "${local.alarm_prefix}-cpu-utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.cpu_threshold
  alarm_description   = "Monitors RDS CPU utilization"
  alarm_actions       = [aws_cloudwatch_event_rule.performance_issue.arn]
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.self_healing.id
  }
  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "free_storage_space" {
  alarm_name          = "${local.alarm_prefix}-free-storage-space"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.free_storage_threshold
  alarm_description   = "Monitors RDS free storage space"
  alarm_actions       = [aws_cloudwatch_event_rule.performance_issue.arn]
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.self_healing.id
  }
  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "database_connections" {
  alarm_name          = "${local.alarm_prefix}-database-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.max_connections_threshold
  alarm_description   = "Monitors RDS database connections"
  alarm_actions       = [aws_cloudwatch_event_rule.performance_issue.arn]
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.self_healing.id
  }
  tags = local.tags
}

# EventBridge rule to trigger healing Lambda on performance issues
resource "aws_cloudwatch_event_rule" "performance_issue" {
  name        = "${local.event_rule_name}-performance"
  description = "Trigger when RDS instance has performance issues"

  event_pattern = jsonencode({
    "source" : ["aws.cloudwatch"],
    "detail-type" : ["CloudWatch Alarm State Change"],
    "resources" : [
      aws_cloudwatch_metric_alarm.cpu_utilization.arn,
      aws_cloudwatch_metric_alarm.free_storage_space.arn,
      aws_cloudwatch_metric_alarm.database_connections.arn
    ],
    "detail" : {
      "state" : {
        "value" : ["ALARM"]
      }
    }
  })

  tags = local.tags
}

# EventBridge rule to periodically check for configuration drift
resource "aws_cloudwatch_event_rule" "config_drift_check" {
  name                = "${local.event_rule_name}-config-drift"
  description         = "Periodically check for RDS configuration drift"
  schedule_expression = "rate(${var.drift_check_interval} minutes)"
  tags                = local.tags
}

# Target for performance issues
resource "aws_cloudwatch_event_target" "performance_lambda" {
  rule      = aws_cloudwatch_event_rule.performance_issue.name
  target_id = "PerformanceLambdaTarget"
  arn       = aws_lambda_function.rds_healing.arn
}

# Target for configuration drift check
resource "aws_cloudwatch_event_target" "config_drift_lambda" {
  rule      = aws_cloudwatch_event_rule.config_drift_check.name
  target_id = "ConfigDriftLambdaTarget"
  arn       = aws_lambda_function.rds_healing.arn
}

# IAM role for RDS monitoring
resource "aws_iam_role" "rds_monitoring_role" {
  name = "${var.name_prefix}-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })

  tags = local.tags
}

# Attach the RDS monitoring policy to the role
resource "aws_iam_role_policy_attachment" "rds_monitoring_attachment" {
  role       = aws_iam_role.rds_monitoring_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# IAM role for Lambda function
resource "aws_iam_role" "lambda_role" {
  name = "${var.name_prefix}-rds-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = local.tags
}

# IAM policy for Lambda function
resource "aws_iam_policy" "lambda_policy" {
  name        = "${var.name_prefix}-rds-lambda-policy"
  description = "Policy for RDS self-healing Lambda function"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Action = [
          "rds:DescribeDBInstances",
          "rds:DescribeDBSnapshots",
          "rds:ModifyDBInstance",
          "rds:RebootDBInstance",
          "rds:RestoreDBInstanceFromDBSnapshot",
          "rds:ListTagsForResource",
          "rds:AddTagsToResource",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:PutMetricData",
          "sns:Publish"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_policy_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# Lambda function for RDS healing
data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/lambda_function.zip"

  source {
    content  = file("${path.module}/lambda/rds_healing.py")
    filename = "rds_healing.py"
  }
}

resource "aws_lambda_function" "rds_healing" {
  function_name    = local.lambda_function_name
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  role             = aws_iam_role.lambda_role.arn
  handler          = "rds_healing.lambda_handler"
  runtime          = "python3.9"
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size

  environment {
    variables = {
      DB_INSTANCE_ID        = aws_db_instance.self_healing.id
      MAX_HEALING_ATTEMPTS  = var.max_healing_attempts
      SNS_TOPIC_ARN         = var.sns_topic_arn
      ORIGINAL_INSTANCE_CLASS = var.instance_class
      ORIGINAL_ALLOCATED_STORAGE = var.allocated_storage
      ORIGINAL_ENGINE_VERSION = var.engine_version
    }
  }

  tags = local.tags
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "performance_permission" {
  statement_id  = "AllowExecutionFromCloudWatchForPerformance"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rds_healing.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.performance_issue.arn
}

resource "aws_lambda_permission" "config_drift_permission" {
  statement_id  = "AllowExecutionFromCloudWatchForConfigDrift"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rds_healing.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.config_drift_check.arn
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${local.lambda_function_name}"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}
