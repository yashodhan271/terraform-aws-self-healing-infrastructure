# Changelog

## v1.1.0 (2025-04-27)

### Improvements

- Enhanced EC2 instance healing logic to better handle transient failures
- Improved RDS performance issue detection with more granular metrics
- Added automatic backup verification for RDS instances
- Optimized Lambda functions for faster response times
- Reduced CloudWatch alarm false positives with improved thresholds
- Enhanced drift detection to ignore planned maintenance changes
- Added support for custom healing actions via Lambda environment variables

### Bug Fixes

- Fixed issue with security group rule restoration when multiple rules were modified
- Resolved race condition in concurrent healing attempts
- Fixed memory leak in long-running Lambda functions
- Corrected error handling for EC2 instances in transitional states
- Fixed SNS notification formatting for better readability
- Resolved issue with RDS storage scaling during high load periods
- Fixed tag propagation during resource healing operations

### Documentation

- Added detailed troubleshooting guide
- Improved usage examples with real-world scenarios
- Added architecture diagrams for better understanding
- Enhanced module input/output documentation

## v1.0.0 (2025-04-26)

- Initial release of the Self-Healing Infrastructure module
- Support for EC2 and RDS self-healing capabilities
- Automatic drift detection and remediation
- CloudWatch integration for monitoring and alerting
- SNS notifications for healing events
