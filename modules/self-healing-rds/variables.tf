variable "name_prefix" {
  description = "Prefix to be used for naming resources"
  type        = string
  default     = "self-healing"
}

variable "instance_identifier" {
  description = "Identifier for the RDS instance"
  type        = string
}

variable "engine" {
  description = "Database engine type"
  type        = string
}

variable "engine_version" {
  description = "Database engine version"
  type        = string
}

variable "instance_class" {
  description = "Instance class for the RDS instance"
  type        = string
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
}

variable "storage_type" {
  description = "Storage type for the RDS instance"
  type        = string
  default     = "gp2"
}

variable "storage_encrypted" {
  description = "Whether to encrypt the storage"
  type        = bool
  default     = true
}

variable "db_name" {
  description = "Name of the database to create"
  type        = string
  default     = null
}

variable "username" {
  description = "Master username for the database"
  type        = string
}

variable "password" {
  description = "Master password for the database"
  type        = string
  sensitive   = true
}

variable "vpc_security_group_ids" {
  description = "List of VPC security group IDs"
  type        = list(string)
}

variable "subnet_ids" {
  description = "List of subnet IDs for the DB subnet group"
  type        = list(string)
}

variable "parameter_group_name" {
  description = "Name of the DB parameter group to associate"
  type        = string
  default     = null
}

variable "backup_retention_period" {
  description = "Number of days to retain backups"
  type        = number
  default     = 7
}

variable "backup_window" {
  description = "Daily time range during which backups are created"
  type        = string
  default     = "03:00-05:00"
}

variable "maintenance_window" {
  description = "Weekly time range during which maintenance can occur"
  type        = string
  default     = "Mon:00:00-Mon:03:00"
}

variable "skip_final_snapshot" {
  description = "Whether to skip final snapshot when the instance is deleted"
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Whether to enable deletion protection"
  type        = bool
  default     = true
}

variable "auto_minor_version_upgrade" {
  description = "Whether to automatically upgrade minor engine versions"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "drift_check_interval" {
  description = "Interval in minutes for checking configuration drift"
  type        = number
  default     = 15
}

variable "max_healing_attempts" {
  description = "Maximum number of healing attempts before giving up"
  type        = number
  default     = 3
}

variable "lambda_timeout" {
  description = "Timeout in seconds for the Lambda function"
  type        = number
  default     = 60
}

variable "lambda_memory_size" {
  description = "Memory size in MB for the Lambda function"
  type        = number
  default     = 128
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 30
}

variable "sns_topic_arn" {
  description = "ARN of the SNS topic for healing notifications"
  type        = string
  default     = ""
}

variable "cpu_threshold" {
  description = "CPU utilization threshold percentage for alarms"
  type        = number
  default     = 80
}

variable "free_storage_threshold" {
  description = "Free storage space threshold in bytes for alarms"
  type        = number
  default     = 5368709120 # 5 GB in bytes
}

variable "max_connections_threshold" {
  description = "Maximum number of connections threshold for alarms"
  type        = number
  default     = 100
}
