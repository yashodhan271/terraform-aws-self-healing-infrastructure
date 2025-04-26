/**
 * # Self-Healing EC2 Module
 *
 * This module deploys an EC2 instance with self-healing capabilities.
 * It automatically detects and recovers from instance failures and configuration drift.
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
  lambda_function_name = "${var.name_prefix}-ec2-healing-function"
  event_rule_name      = "${var.name_prefix}-ec2-healing-rule"
  alarm_name           = "${var.name_prefix}-ec2-status-check-failed"
  tags = merge(
    var.tags,
    {
      "ManagedBy" = "terraform"
      "Module"    = "self-healing-ec2"
    }
  )
}

# EC2 Instance
resource "aws_instance" "self_healing" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = var.vpc_security_group_ids
  key_name               = var.key_name
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  user_data = var.user_data

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = var.root_volume_type
    encrypted   = var.encrypt_volumes
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tags = merge(
    local.tags,
    {
      "Name" = var.instance_name
    }
  )

  # Store the original configuration as tags for drift detection
  lifecycle {
    ignore_changes = [
      ami,
      user_data,
      tags["LastHealed"],
      tags["HealingAttempts"]
    ]
  }
}

# Enable detailed monitoring for the instance
resource "aws_cloudwatch_metric_alarm" "status_check_failed" {
  alarm_name          = local.alarm_name
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "This metric monitors ec2 status checks"
  alarm_actions       = [aws_cloudwatch_event_rule.status_check_failed.arn]
  dimensions = {
    InstanceId = aws_instance.self_healing.id
  }
  tags = local.tags
}

# EventBridge rule to trigger healing Lambda on status check failure
resource "aws_cloudwatch_event_rule" "status_check_failed" {
  name        = "${local.event_rule_name}-status-check"
  description = "Trigger when EC2 instance status check fails"

  event_pattern = jsonencode({
    "source" : ["aws.cloudwatch"],
    "detail-type" : ["CloudWatch Alarm State Change"],
    "resources" : [aws_cloudwatch_metric_alarm.status_check_failed.arn],
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
  description         = "Periodically check for EC2 configuration drift"
  schedule_expression = "rate(${var.drift_check_interval} minutes)"
  tags                = local.tags
}

# Target for status check failure
resource "aws_cloudwatch_event_target" "status_check_lambda" {
  rule      = aws_cloudwatch_event_rule.status_check_failed.name
  target_id = "StatusCheckLambdaTarget"
  arn       = aws_lambda_function.ec2_healing.arn
}

# Target for configuration drift check
resource "aws_cloudwatch_event_target" "config_drift_lambda" {
  rule      = aws_cloudwatch_event_rule.config_drift_check.name
  target_id = "ConfigDriftLambdaTarget"
  arn       = aws_lambda_function.ec2_healing.arn
}

# IAM role for EC2 instance
resource "aws_iam_role" "ec2_role" {
  name = "${var.name_prefix}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = local.tags
}

# IAM instance profile for EC2
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.name_prefix}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# IAM policy for EC2 instance
resource "aws_iam_policy" "ec2_policy" {
  name        = "${var.name_prefix}-ec2-policy"
  description = "Policy for self-healing EC2 instance"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "cloudwatch:PutMetricData",
          "ec2:DescribeTags",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach policy to EC2 role
resource "aws_iam_role_policy_attachment" "ec2_policy_attachment" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_policy.arn
}

# IAM role for Lambda function
resource "aws_iam_role" "lambda_role" {
  name = "${var.name_prefix}-lambda-role"

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
  name        = "${var.name_prefix}-lambda-policy"
  description = "Policy for EC2 self-healing Lambda function"

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
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ec2:StartInstances",
          "ec2:StopInstances",
          "ec2:RebootInstances",
          "ec2:DescribeTags",
          "ec2:CreateTags",
          "ec2:ModifyInstanceAttribute",
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

# Lambda function for EC2 healing
data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/lambda_function.zip"

  source {
    content  = file("${path.module}/lambda/ec2_healing.py")
    filename = "ec2_healing.py"
  }
}

resource "aws_lambda_function" "ec2_healing" {
  function_name    = local.lambda_function_name
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  role             = aws_iam_role.lambda_role.arn
  handler          = "ec2_healing.lambda_handler"
  runtime          = "python3.9"
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size

  environment {
    variables = {
      INSTANCE_ID            = aws_instance.self_healing.id
      MAX_HEALING_ATTEMPTS   = var.max_healing_attempts
      SNS_TOPIC_ARN          = var.sns_topic_arn
      ORIGINAL_AMI           = var.ami_id
      ORIGINAL_INSTANCE_TYPE = var.instance_type
      ORIGINAL_USER_DATA     = var.user_data != null ? base64encode(var.user_data) : ""
    }
  }

  tags = local.tags
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "status_check_permission" {
  statement_id  = "AllowExecutionFromCloudWatchForStatusCheck"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ec2_healing.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.status_check_failed.arn
}

resource "aws_lambda_permission" "config_drift_permission" {
  statement_id  = "AllowExecutionFromCloudWatchForConfigDrift"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ec2_healing.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.config_drift_check.arn
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${local.lambda_function_name}"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}
