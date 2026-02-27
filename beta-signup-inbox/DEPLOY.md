# Deployment (AWS App Runner)

## Prerequisites

- AWS CLI configured (`aws sso login`)
- Docker installed
- ECR repository created
- App Runner service created with environment variables configured

## 1. Create ECR Repo (one-time)

```bash
aws ecr create-repository --repository-name beta-signup-inbox --region us-east-1
```

## 2. Build & Push

```bash
# Build for x86_64 (required for App Runner)
docker build --platform linux/amd64 -t beta-signup-inbox .

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# Tag and push
docker tag beta-signup-inbox:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/beta-signup-inbox:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/beta-signup-inbox:latest
```

## 3. Create App Runner Service (one-time)

Create via AWS Console or CLI. Configure these environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SEMA_WEBHOOK_SECRET` | Yes | Webhook verification secret |
| `SEMA_API_KEY` | Yes | Sema API key for /signup |
| `SEMA_INBOX_ID` | Yes | Sema inbox UUID |
| `SEMA_BASE_URL` | Yes | `https://dev-api.withsema.com` |
| `RESEND_API_KEY` | Yes | Resend API key |
| `RESEND_FROM_EMAIL` | Yes | `beta@out.withsema.com` |
| `RESEND_REPLY_TO` | No | Defaults to `beta@dev-in.withsema.com` |
| `CALCOM_LINK` | No | Defaults to cal.com link |
| `GENERATE_IMAGE` | No | `true` to enable image generation |
| `GOOGLE_API_KEY` | If images | Google AI Studio key |
| `S3_BUCKET` | If images | S3 bucket for images |
| `S3_REGION` | If images | Defaults to `us-east-1` |

Port: **5050**

## 4. Redeploy

```bash
aws apprunner start-deployment --service-arn <SERVICE_ARN>
```

## 5. Post-Deploy

1. Update the Sema inbox webhook URL to `https://<SERVICE_URL>/webhook`
2. Point your frontend signup form to `https://<SERVICE_URL>/signup`

Store your `SERVICE_ARN`, `SERVICE_ID`, and `SERVICE_URL` in `.env.deploy` (gitignored).
