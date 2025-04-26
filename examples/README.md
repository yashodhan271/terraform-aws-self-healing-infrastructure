# Self-Healing Infrastructure Examples

This directory contains examples demonstrating how to use the self-healing infrastructure module in different scenarios.

## Examples

- **[Complete Example](./complete/)**: A comprehensive example showing how to deploy a self-healing EC2 instance with monitoring and notifications.

## Prerequisites

- Terraform >= 1.0.0
- AWS CLI configured with appropriate credentials
- AWS account with permissions to create the required resources

## Usage

Each example can be deployed independently. Navigate to the example directory and run:

```bash
# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply the configuration
terraform apply
```

## Testing Self-Healing Capabilities

After deploying an example, you can test the self-healing capabilities using the following methods:

### Testing EC2 Self-Healing

1. **Simulate Status Check Failure**:
   ```bash
   # Get the instance ID
   INSTANCE_ID=$(terraform output -raw instance_id)
   
   # Use AWS Systems Manager to stop the instance service (requires SSM agent)
   aws ssm send-command \
     --document-name "AWS-RunShellScript" \
     --parameters "commands=['systemctl stop amazon-ssm-agent']" \
     --targets "Key=instanceids,Values=$INSTANCE_ID"
   ```

2. **Introduce Configuration Drift**:
   ```bash
   # Change the instance type (this will trigger drift detection)
   aws ec2 modify-instance-attribute \
     --instance-id $INSTANCE_ID \
     --instance-type "{\"Value\": \"t3.small\"}"
   ```

3. **Monitor Healing Actions**:
   - Check the CloudWatch dashboard (URL in the outputs)
   - Review Lambda function logs
   - Check your email for healing notifications (if configured)

## Cleanup

To remove all resources created by an example:

```bash
terraform destroy
```

## Notes

- The self-healing process may take a few minutes to detect and remediate issues
- Some healing actions require the instance to be stopped and started, which can cause brief downtime
- For production use, consider adjusting the healing parameters based on your requirements
