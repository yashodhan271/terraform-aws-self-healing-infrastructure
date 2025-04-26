/**
 * # Complete Self-Healing Infrastructure Example
 *
 * This example demonstrates how to use the self-healing infrastructure module
 * to deploy EC2 instances with automatic recovery capabilities.
 */

provider "aws" {
  region = var.region
}

# Create a VPC for our self-healing infrastructure
module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
  version = "~> 3.0"

  name = "${var.name_prefix}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.region}a", "${var.region}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true

  tags = var.tags
}

# Create a security group for our EC2 instance
resource "aws_security_group" "instance_sg" {
  name        = "${var.name_prefix}-instance-sg"
  description = "Security group for self-healing EC2 instance"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH access"
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP access"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = var.tags
}

# Create a self-healing EC2 instance
module "self_healing_ec2" {
  source = "../../modules/self-healing-ec2"

  name_prefix            = var.name_prefix
  instance_name          = "${var.name_prefix}-web-server"
  ami_id                 = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = module.vpc.public_subnets[0]
  vpc_security_group_ids = [aws_security_group.instance_sg.id]
  key_name               = var.key_name

  user_data = <<-EOF
    #!/bin/bash
    echo "Hello from self-healing EC2 instance" > /var/tmp/hello.txt
    yum update -y
    yum install -y httpd
    systemctl start httpd
    systemctl enable httpd
    echo "<h1>Self-Healing Infrastructure Example</h1><p>This instance will automatically recover from failures!</p>" > /var/www/html/index.html
    EOF

  root_volume_size     = 10
  root_volume_type     = "gp3"
  encrypt_volumes      = true
  drift_check_interval = 15
  max_healing_attempts = 3
  
  # Create an SNS topic for notifications
  sns_topic_arn = aws_sns_topic.healing_notifications.arn

  tags = var.tags
}

# Create an SNS topic for healing notifications
resource "aws_sns_topic" "healing_notifications" {
  name = "${var.name_prefix}-healing-notifications"
  tags = var.tags
}

# Optional: Subscribe an email to the SNS topic
resource "aws_sns_topic_subscription" "email_subscription" {
  count     = var.notification_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.healing_notifications.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# Create a CloudWatch dashboard to monitor the self-healing infrastructure
resource "aws_cloudwatch_dashboard" "self_healing_dashboard" {
  dashboard_name = "${var.name_prefix}-dashboard"
  
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
            ["AWS/EC2", "StatusCheckFailed", "InstanceId", module.self_healing_ec2.instance_id],
            ["AWS/EC2", "StatusCheckFailed_Instance", "InstanceId", module.self_healing_ec2.instance_id],
            ["AWS/EC2", "StatusCheckFailed_System", "InstanceId", module.self_healing_ec2.instance_id]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.region
          title   = "EC2 Status Checks"
          period  = 60
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
            ["AWS/EC2", "CPUUtilization", "InstanceId", module.self_healing_ec2.instance_id]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.region
          title   = "EC2 CPU Utilization"
          period  = 60
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", module.self_healing_ec2.lambda_function_name],
            ["AWS/Lambda", "Errors", "FunctionName", module.self_healing_ec2.lambda_function_name]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.region
          title   = "Self-Healing Lambda Metrics"
          period  = 60
        }
      }
    ]
  })
}
