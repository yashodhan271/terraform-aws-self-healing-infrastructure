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

variable "ami_id" {
  description = "AMI ID for the EC2 instance"
  type        = string
  default     = "ami-0c55b159cbfafe1f0" # Amazon Linux 2 AMI (HVM), SSD Volume Type
}

variable "instance_type" {
  description = "Instance type for the EC2 instance"
  type        = string
  default     = "t3.micro"
}

variable "key_name" {
  description = "Name of the key pair to use for SSH access"
  type        = string
  default     = null
}

variable "notification_email" {
  description = "Email address to receive healing notifications"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Environment = "demo"
    Project     = "self-healing-infrastructure"
    ManagedBy   = "terraform"
  }
}
