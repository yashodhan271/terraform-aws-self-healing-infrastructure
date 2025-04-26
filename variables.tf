variable "region" {
  description = "AWS region where resources will be deployed"
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix to be used for naming resources"
  type        = string
  default     = "self-healing"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "enable_notifications" {
  description = "Whether to enable SNS notifications for healing events"
  type        = bool
  default     = true
}

variable "create_dashboard" {
  description = "Whether to create a CloudWatch dashboard for monitoring self-healing metrics"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 30
}

variable "healing_check_interval" {
  description = "Interval in minutes for checking resource health and configuration"
  type        = number
  default     = 5
}

variable "max_healing_attempts" {
  description = "Maximum number of healing attempts before giving up"
  type        = number
  default     = 3
}

variable "healing_timeout_seconds" {
  description = "Timeout in seconds for healing operations"
  type        = number
  default     = 300
}
