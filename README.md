# Arc XP Log Forwarding to AWS CloudWatch

## Overview

This guide outlines the step-by-step process for configuring an Arc XP client’s AWS account to receive logs from Arc XP's Fusion rendering engine.

While Arc XP personnel will handle the **CloudWatch Logs subscription filter** configuration within the client’s Arc XP environment, this document focuses solely on the actions the customer must take to prepare their AWS environment for receiving and managing logs.

The guide includes detailed instructions on:

- Setting up a **Kinesis Data Stream**
- Creating the necessary **IAM roles and policies**
- Configuring the **CloudWatch Logs destination**
- Deploying resources using the **AWS CLI**


Additionally, the solution includes an optional **AWS Lambda function** that enables streaming of logs content to **CloudWatch Logs** and/or **Amazon S3** within the customer’s receiving account.

*Note:* The aws region for the destination account must match the Arc XP Platform deployment region 

## Prerequisites
Before you begin, ensure you have the following:
- An AWS account with necessary permissions.
- AWS CLI installed and configured.

## Step-by-Step Setup

### 1. Create a Kinesis Data Stream
Kinesis Data Stream will act as the intermediary where logs are forwarded before being processed. Creating a Kinesis stream ensures that log data is handled efficiently and can be accessed by CloudWatch.

```sh
aws kinesis create-stream --stream-name "ArcXPDestinationLogStream" --shard-count 1
```

Wait until the stream becomes active. You can check the stream status with:

```sh
aws kinesis describe-stream --stream-name "ArcXPDestinationLogStream"
```

Take note of the `StreamARN` value, as it will be needed in later steps.

### 2. Establish IAM Trust Policy
CloudWatch Logs needs permission to assume a role in your AWS account to forward logs. We create an IAM trust policy to grant this access.

Create the trust policy file before proceeding:

```sh
cat > trust-policy.json << EOL
{
  "Statement": {
    "Effect": "Allow",
    "Principal": {
      "Service": "logs.amazonaws.com"
    },
    "Condition": {
      "StringLike": {
        "aws:SourceArn": [
          "arn:aws:logs:<region>:<sourceAccountId>:*",
          "arn:aws:logs:<region>:<destinationAccountId>:*"
        ]
      }
    },
    "Action": "sts:AssumeRole"
  }
}
EOL
```

### 3. Create IAM Role with Permissions
An IAM role is required for CloudWatch Logs to forward data to Kinesis. We create the role and attach the necessary permissions to allow `PutRecord` operations on the Kinesis stream.

```sh
# Create the IAM role
aws iam create-role --role-name ArcXPLogForwardingRole --assume-role-policy-document file://trust-policy.json

# Define the permissions policy before proceeding
cat > permissions-policy.json << EOL
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "kinesis:PutRecord",
      "Resource": "arn:aws:kinesis:<region>:<destinationAccountId>:stream/ArcXPDestinationLogStream"
    }
  ]
}
EOL

# Attach the permissions policy to the role
aws iam put-role-policy --role-name ArcXPLogForwardingRole --policy-name Permissions-Policy-For-CWL --policy-document file://permissions-policy.json
```

Replace `<region>`, `<sourceAccountId>`, and `<destinationAccountId>` with the respective AWS values.

### 4. Configure the CloudWatch Logs Destination
The CloudWatch Logs destination must be configured to send logs to the Kinesis stream.

```sh
aws logs put-destination \
    --destination-name ArcXPLogDestination \
    --target-arn arn:aws:kinesis:<region>:<destinationAccountId>:stream/ArcXPDestinationLogStream \
    --role-arn arn:aws:iam::<destinationAccountId>:role/ArcXPLogForwardingRole
```

### 5. Create the Access Policy File
CloudWatch Logs destinations require an access policy that allows the log sender account to forward logs. This policy must explicitly grant `logs:PutSubscriptionFilter` permission.

Create the access policy file before proceeding:

```sh
cat > access-policy.json << EOL
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": "<sourceAccountId>"},
      "Action": "logs:PutSubscriptionFilter",
      "Resource": "arn:aws:logs:<region>:<destinationAccountId>:destination:ArcXPLogDestination"
    }
  ]
}
EOL
```

### 6. Set Destination Policy
Now that the `access-policy.json` file has been created, we apply it to the CloudWatch Logs destination to finalize the configuration.

```sh
aws logs put-destination-policy \
    --destination-name ArcXPLogDestination \
    --access-policy file://access-policy.json
```

## Deploying the AWS Lambda Function with AWS SAM

### Important: Replace Placeholders in `template.yaml`
Before deploying the Lambda function, ensure that all placeholders in the `template.yaml` file are replaced with your specific AWS account details. The placeholders include:

- `<aws-account-id>`: Replace with your AWS account ID.
- `<region>`: Replace with the AWS region where you want to deploy the resources.

Ensure these placeholders are correctly replaced to avoid deployment errors.

### Step 1: Install AWS SAM CLI
Ensure you have the AWS SAM CLI installed. You can follow the installation guide from the [AWS SAM CLI documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html).

### Step 2: Build the Lambda Function
Use the SAM CLI to build the Lambda function. This command will package your application and its dependencies.

```bash
sam build
```

### Step 3: Deploy the Lambda Function
Deploy the function using the SAM CLI. This command will package and deploy your application to AWS, creating the necessary resources.

```bash
sam deploy --guided
```

During the guided deployment, you will be prompted to enter parameters such as the stack name, AWS region, and whether to save the configuration for future deployments.

### Step 4: Verify the Deployment
After deployment, verify that the Lambda function is created and configured correctly in the AWS Management Console.

<img width="1395" alt="image" src="https://github.com/user-attachments/assets/5fdbf448-f51d-4c73-a2c7-31e749dafedf" />



## Troubleshooting
### Common Issues and Fixes
- **Logs not appearing in CloudWatch**: Verify IAM role permissions, Kinesis stream configuration, and subscription filters.
- **Access Denied Errors**: Check the CloudWatch destination policy and IAM role permissions.





## Resources
- [AWS CloudWatch Log Destination Documentation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CreateDestination.html)
