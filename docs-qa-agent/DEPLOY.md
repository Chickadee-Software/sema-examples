# Deployment (AWS App Runner)

Deploy to AWS App Runner for our beta.

## Prerequisites

- AWS CLI configured (`aws sso login`)
- Docker installed
- ECR repository created (`aws ecr create-repository --repository-name docs-qa-demo --region us-east-1`)
- App Runner service created with environment variables configured

## Build & Push

```bash
# Build for x86_64 (required for App Runner)
docker build --platform linux/amd64 -t docs-qa-demo .

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# Tag and push
docker tag docs-qa-demo:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/docs-qa-demo:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/docs-qa-demo:latest
```

## Redeploy

```bash
aws apprunner start-deployment --service-arn <SERVICE_ARN>
```

## Check Status

```bash
aws apprunner describe-service --service-arn <SERVICE_ARN> --query "Service.Status"
```

## View Logs

```bash
# List log streams
aws logs describe-log-streams \
  --log-group-name "/aws/apprunner/<SERVICE_NAME>/<SERVICE_ID>/application" \
  --order-by LastEventTime --descending --limit 1

# Get recent logs
aws logs get-log-events \
  --log-group-name "/aws/apprunner/<SERVICE_NAME>/<SERVICE_ID>/application" \
  --log-stream-name "<STREAM_NAME>"
```

## Configuration

Store your actual `ACCOUNT_ID`, `SERVICE_ARN`, and `SERVICE_ID` in `.env.deploy` (gitignored).
