# Deployment (AWS App Runner)

Deploy to AWS App Runner for our beta.

## Prerequisites

- AWS CLI configured (`aws sso login`)
- Docker installed
- ECR repository created (`aws ecr create-repository --repository-name docs-qa-demo --region us-east-1`)
- App Runner service created with environment variables configured (see [Environment variables](#environment-variables) below)

## Environment variables

The container needs these environment variables. Set them on the App Runner service (they are **not** baked into the image).

- **SEMA_WEBHOOK_SECRET** (required) – Webhook secret from your Sema inbox settings  
- **OPENAI_API_KEY** (required) – OpenAI API key  
- **RESEND_API_KEY** (required) – Resend API key  
- **RESEND_FROM_EMAIL** (required) – From address for replies (e.g. `docs-qa@out.withsema.com`)  
- **RESEND_REPLY_TO** (required) – Reply-To; must match your inbox (e.g. `docs-qa@dev-in.withsema.com` for dev)  
- **DOCS_CONTEXT_URL** (optional) – Default: `https://docs.withsema.com/llm-context.json`

**How to set or update them:**

- **Console (easiest):** [App Runner console](https://console.aws.amazon.com/apprunner) → your service → **Configuration** tab → **Edit** → **Service settings** → **Environment variables**. Add each key/value, then **Save changes**. App Runner will redeploy with the new env.
- **CLI:** Use `aws apprunner update-service` with `--source-configuration` including `ImageRepository.ImageConfiguration.RuntimeEnvironmentVariables`. You must pass the full source config (get current with `describe-service`, merge env vars, then `update-service`). For one-off edits, the Console is simpler.

After changing env vars or pushing a new image, trigger a deployment so the service picks them up (see Redeploy below).

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
Environment variable **values** (secrets, API keys, etc.) are set on the App Runner service itself (Console or CLI), not in `.env.deploy`.
