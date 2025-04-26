<!-- BEGIN_TF_DOCS -->
<p align="center">
  <img src="https://raw.githubusercontent.com/yashodhan271/terraform-aws-self-healing-infrastructure/main/logo.svg" alt="Self-Healing Infrastructure" width="200"/>
</p>

# Self-Healing Infrastructure Terraform Module

A Terraform module that deploys cloud resources with built-in self-healing capabilities. This module monitors deployed resources and automatically repairs them when failures or configuration drift are detected, without requiring manual intervention.

## Features

- **Automatic Drift Detection**: Continuously monitors infrastructure for configuration drift
- **Self-Healing Capabilities**: Automatically restores resources to their desired state
- **Comprehensive Monitoring**: Integrates with AWS CloudWatch for real-time alerts and metrics
- **Modular Design**: Easily add self-healing capabilities to different resource types
- **Minimal Operational Overhead**: Reduces the need for manual intervention and maintenance

## Supported Resources

- **EC2 Instances**: Auto-recovery from instance failures, health checks, and configuration drift
- **RDS Databases**: Automatic backup, restore, and configuration management
- **Security Groups**: Drift detection and automatic rule restoration

## Usage

```hcl
# From Terraform Registry (recommended)
module "self_healing_ec2" {
  source  = "yashodhan271/aws-self-healing-infrastructure/aws"
  version = "1.0.0"

  instance_name        = "web-server"
  instance_type        = "t3.micro"
  ami_id               = "ami-0c55b159cbfafe1f0"
  subnet_id            = "subnet-abcdef123456"
  vpc_security_group_ids = ["sg-abcdef123456"]
  
  enable_self_healing  = true
  health_check_path    = "/health"
  recovery_attempts    = 3
  
  tags = {
    Environment = "Production"
    Project     = "WebApp"
  }
}

# From GitHub
module "self_healing_ec2" {
  source = "github.com/yashodhan271/terraform-aws-self-healing-infrastructure/modules/self-healing-ec2"

  # Module variables...
}
```

## Unique Features & Advantages

### Why This Module Is Different

Most infrastructure management solutions require external monitoring tools, manual intervention, or complex orchestration systems to detect and fix issues. This module takes a fundamentally different approach:

1. **Built-In Self-Healing**: Unlike traditional Terraform modules that only deploy resources, this module embeds healing capabilities directly within the infrastructure it creates.

2. **No External Dependencies**: Doesn't rely on external monitoring tools like Datadog, New Relic, or Prometheus - everything is self-contained using native AWS services.

3. **Proactive vs. Reactive**: Instead of waiting for alerts that require human intervention, this module automatically detects and fixes issues in real-time.

4. **Configuration Drift Protection**: Automatically detects and reverts unauthorized changes to your infrastructure, maintaining your desired state without requiring `terraform apply`.

5. **Reduced Mean Time To Recovery (MTTR)**: Healing actions happen within minutes of detecting an issue, dramatically reducing downtime.

6. **Comprehensive Observability**: Provides detailed logs and metrics about healing events, giving you visibility without requiring manual intervention.

## Detailed Usage Guide

### Getting Started

1. **Basic Implementation**

```hcl
# From Terraform Registry (recommended)
module "self_healing_infrastructure" {
  source  = "yashodhan271/aws-self-healing-infrastructure/aws"
  version = "1.0.0"

  region      = "us-east-1"
  name_prefix = "production"
  
  enable_notifications = true
  create_dashboard     = true
  
  tags = {
    Environment = "Production"
    Project     = "Core Infrastructure"
  }
}

# From GitHub
module "self_healing_infrastructure" {
  source = "github.com/yashodhan271/terraform-aws-self-healing-infrastructure"

  # Module variables...
}
```

2. **Deploying Self-Healing EC2 Instances**

```hcl
# From Terraform Registry (recommended)
module "web_servers" {
  source  = "yashodhan271/aws-self-healing-infrastructure/aws"
  version = "1.0.0"

  name_prefix            = "web"
  instance_name          = "web-server"
  ami_id                 = "ami-0c55b159cbfafe1f0"
  instance_type          = "t3.medium"
  subnet_id              = module.vpc.public_subnets[0]
  vpc_security_group_ids = [aws_security_group.web.id]
  
  # Self-healing configuration
  drift_check_interval = 10  # minutes
  max_healing_attempts = 3
  sns_topic_arn        = aws_sns_topic.alerts.arn
  
  tags = {
    Service = "WebApp"
  }
}

# From GitHub
module "web_servers" {
  source = "github.com/yashodhan271/terraform-aws-self-healing-infrastructure/modules/self-healing-ec2"

  # Module variables...
}
```

3. **Deploying Self-Healing RDS Databases**

```hcl
# From Terraform Registry (recommended)
module "database" {
  source  = "yashodhan271/aws-self-healing-infrastructure/aws"
  version = "1.0.0"

  name_prefix         = "db"
  instance_identifier = "production-mysql"
  engine              = "mysql"
  engine_version      = "8.0"
  instance_class      = "db.t3.medium"
  allocated_storage   = 50
  
  username               = "admin"
  password               = var.db_password
  vpc_security_group_ids = [aws_security_group.db.id]
  subnet_ids             = module.vpc.database_subnets
  
  # Self-healing configuration
  drift_check_interval = 15  # minutes
  max_healing_attempts = 3
  cpu_threshold        = 80  # percent
  sns_topic_arn        = aws_sns_topic.alerts.arn
  
  tags = {
    Service = "Database"
  }
}

# From GitHub
module "database" {
  source = "github.com/yashodhan271/terraform-aws-self-healing-infrastructure/modules/self-healing-rds"

  # Module variables...
}
```

### Advanced Usage

#### Customizing Healing Behavior

You can customize the healing behavior for different environments:

```hcl
# Development environment: more lenient thresholds
module "dev_database" {
  source = "github.com/yashodhan271/terraform-aws-self-healing-infrastructure/modules/self-healing-rds"
  
  # Basic configuration...
  
  # More lenient healing configuration
  drift_check_interval     = 30  # minutes
  max_healing_attempts     = 5
  cpu_threshold            = 90  # percent
  free_storage_threshold   = 1073741824  # 1 GB in bytes
  max_connections_threshold = 200
}

# Production environment: stricter thresholds
module "prod_database" {
  source = "github.com/yashodhan271/terraform-aws-self-healing-infrastructure/modules/self-healing-rds"
  
  # Basic configuration...
  
  # Stricter healing configuration
  drift_check_interval     = 5   # minutes
  max_healing_attempts     = 2
  cpu_threshold            = 70  # percent
  free_storage_threshold   = 5368709120  # 5 GB in bytes
  max_connections_threshold = 80
}
```

#### Integrating with Existing Monitoring

While the module is self-contained, you can integrate it with your existing monitoring systems:

```hcl
# Forward healing notifications to an existing monitoring system
resource "aws_sns_topic_subscription" "forward_to_pagerduty" {
  topic_arn = module.self_healing_infrastructure.sns_topic_arn
  protocol  = "https"
  endpoint  = "https://events.pagerduty.com/integration/abcdef123456/enqueue"
}
```

## How Self-Healing Works

### EC2 Self-Healing

1. **Status Check Failures**:
   - CloudWatch alarms detect when EC2 status checks fail
   - Lambda function attempts to reboot the instance
   - If reboot fails, the instance is stopped and started
   - If the issue persists, the Lambda function can terminate and recreate the instance

2. **Configuration Drift**:
   - Scheduled Lambda function checks instance configuration against desired state
   - Detects changes to instance type, security groups, tags, etc.
   - Automatically reverts unauthorized changes
   - Records drift events and healing actions in CloudWatch Logs

3. **Performance Issues**:
   - CloudWatch alarms monitor CPU, memory, and disk metrics
   - When thresholds are exceeded, Lambda function takes appropriate action
   - Actions include scaling vertically, optimizing resources, or rebooting

### RDS Self-Healing

1. **Database Failures**:
   - Monitors RDS status and performance metrics
   - Automatically reboots the instance if it becomes unresponsive
   - Can initiate failover to a standby instance if available

2. **Storage Issues**:
   - Monitors free storage space and disk I/O
   - Automatically increases allocated storage when running low
   - Optimizes storage performance based on workload

3. **Configuration Drift**:
   - Detects changes to instance class, parameter groups, security groups
   - Automatically reverts to the desired configuration
   - Prevents unauthorized changes from affecting database performance

## Comparison with Other Solutions

| Feature | This Module | AWS Auto Recovery | Terraform Cloud | Manual Monitoring |
|---------|-------------|------------------|-----------------|-------------------|
| Automatic recovery from failures | ✅ | ✅ (limited) | ❌ | ❌ |
| Configuration drift detection | ✅ | ❌ | ✅ (drift detection only) | ❌ |
| Automatic drift remediation | ✅ | ❌ | ❌ (requires manual apply) | ❌ |
| Performance-based healing | ✅ | ❌ | ❌ | ❌ |
| Customizable healing logic | ✅ | ❌ | ❌ | ✅ |
| No external dependencies | ✅ | ✅ | ❌ | ❌ |
| Detailed healing metrics | ✅ | ❌ | ❌ | ❌ |
| Native AWS integration | ✅ | ✅ | ❌ | ❌ |

## Best Practices

1. **Start Small**: Begin by implementing self-healing for your most critical resources.

2. **Monitor Healing Events**: Review the CloudWatch logs and metrics to understand healing patterns.

3. **Adjust Thresholds**: Fine-tune thresholds based on your application's behavior and requirements.

4. **Test Healing Scenarios**: Deliberately introduce failures in non-production environments to verify healing works as expected.

5. **Combine with IaC Best Practices**: Use this module alongside other Terraform best practices like state locking, versioning, and CI/CD pipelines.

## Limitations and Considerations

- **AWS-Specific**: This module is designed specifically for AWS resources.
- **Stateful Resources**: Some healing actions may cause brief downtime for stateful resources.
- **Complex Failures**: Extremely complex failure scenarios might still require manual intervention.
- **Cost Considerations**: The Lambda functions and CloudWatch alarms will incur some AWS charges.

## Roadmap

Future enhancements planned for this module:

- Support for additional AWS resource types (ECS, EKS, Lambda)
- Multi-region healing capabilities
- Enhanced machine learning for predictive healing
- Integration with AWS Control Tower and Organizations
- Support for cross-account healing

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.0.0 |
| aws | >= 4.0.0 |

## Providers

| Name | Version |
|------|---------|
| aws | >= 4.0.0 |
| archive | >= 2.0.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| region | AWS region where resources will be deployed | `string` | `"us-east-1"` | no |
| name_prefix | Prefix to be used for naming resources | `string` | `"self-healing"` | no |
| tags | Tags to apply to all resources | `map(string)` | `{}` | no |
| enable_notifications | Whether to enable SNS notifications for healing events | `bool` | `true` | no |
| create_dashboard | Whether to create a CloudWatch dashboard for monitoring self-healing metrics | `bool` | `true` | no |
| log_retention_days | Number of days to retain CloudWatch logs | `number` | `30` | no |
| healing_check_interval | Interval in minutes for checking resource health and configuration | `number` | `5` | no |
| max_healing_attempts | Maximum number of healing attempts before giving up | `number` | `3` | no |
| healing_timeout_seconds | Timeout in seconds for healing operations | `number` | `300` | no |

## Outputs

| Name | Description |
|------|-------------|
| sns_topic_arn | ARN of the SNS topic for healing notifications |
| dashboard_name | Name of the CloudWatch dashboard for monitoring self-healing metrics |
| module_version | Version of the self-healing infrastructure module |

## License

MIT
<!-- END_TF_DOCS -->
