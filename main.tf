/**
 * # Self-Healing Infrastructure Module
 *
 * This module orchestrates the deployment of self-healing infrastructure components.
 * It provides a unified interface for deploying various self-healing resources.
 */

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# Optional SNS topic for notifications about healing events
resource "aws_sns_topic" "healing_notifications" {
  count = var.enable_notifications ? 1 : 0
  name  = "${var.name_prefix}-healing-notifications"
  tags  = var.tags
}

# Optional CloudWatch dashboard for monitoring self-healing metrics
resource "aws_cloudwatch_dashboard" "self_healing_dashboard" {
  count          = var.create_dashboard ? 1 : 0
  dashboard_name = "${var.name_prefix}-self-healing-dashboard"
  
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", "SelfHealingFunction"],
            ["AWS/Lambda", "Errors", "FunctionName", "SelfHealingFunction"]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.region
          title   = "Self-Healing Function Metrics"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Events", "TriggeredRules", "RuleName", "${var.name_prefix}-healing-rule"]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.region
          title   = "Healing Events Triggered"
          period  = 300
        }
      }
    ]
  })
}
