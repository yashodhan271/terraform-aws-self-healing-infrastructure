variable "name_prefix" {
  description = "Prefix to be used for naming resources"
  type        = string
  default     = "self-healing"
}

variable "instance_name" {
  description = "Name of the EC2 instance"
  type        = string
}

variable "ami_id" {
  description = "AMI ID for the EC2 instance"
  type        = string
}

variable "instance_type" {
  description = "Instance type for the EC2 instance"
  type        = string
  default     = "t3.micro"
}

variable "subnet_id" {
  description = "Subnet ID where the EC2 instance will be deployed"
  type        = string
}

variable "vpc_security_group_ids" {
  description = "List of security group IDs for the EC2 instance"
  type        = list(string)
}

variable "key_name" {
  description = "Name of the key pair to use for SSH access"
  type        = string
  default     = null
}

variable "user_data" {
  description = "User data script for the EC2 instance"
  type        = string
  default     = null
}

variable "root_volume_size" {
  description = "Size of the root volume in GB"
  type        = number
  default     = 8
}

variable "root_volume_type" {
  description = "Type of the root volume"
  type        = string
  default     = "gp3"
}

variable "encrypt_volumes" {
  description = "Whether to encrypt the EBS volumes"
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
