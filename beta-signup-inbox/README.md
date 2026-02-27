# Beta Signup Inbox

Landing page CTA → Sema Inbox → auto-reply with Cal.com booking link + AI-generated welcome image.

## How It Works

```
User clicks "Get your API key" on landing page
       ↓
  Frontend POSTs email to /signup
       ↓
  App uploads item to Sema Inbox via SDK
       ↓
  Sema processes → fires ITEM_READY webhook
       ↓
  This App (verify signature)
       ↓
  Gemini generates welcome image (optional) → S3
       ↓
  Resend → Reply with Cal.com booking link
```

## Setup

1. **Get a Sema inbox** with `email_enabled=True` and webhook URL pointing to this app
2. **Get a Sema API key** for the `/signup` endpoint
3. **Verify outbound domain** in Resend (`out.withsema.com`)
4. **Copy `.env.example` to `.env`** and fill in your values
5. **Install deps**: `make install`
6. **Run**: `make run`

### Image Generation (Optional)

To include an AI-generated welcome image in each reply:

1. Get a [Google AI Studio](https://aistudio.google.com/) API key
2. Have an S3 bucket for hosting the images
3. Set these in `.env`:
   ```
   GENERATE_IMAGE=true
   GOOGLE_API_KEY=AIza...
   S3_BUCKET=your-bucket
   S3_REGION=us-east-1
   ```

Images are uploaded to S3 and included via presigned URL (30-day expiry).

### Webhook URL: Local vs Cloud

This app listens on `http://localhost:5050/webhook`.

| Your Setup | Webhook URL |
|------------|-------------|
| Sema running locally | `http://localhost:5050/webhook` (direct) |
| Sema cloud (dev-api.withsema.com) | Use [ngrok](https://ngrok.com) or similar |

**For cloud Sema**, expose your local app first:

```bash
ngrok http 5050
# Use the https://xxx.ngrok.io/webhook URL in your inbox settings
```

## Deployment

See the Dockerfile for container-based deployment (e.g. AWS App Runner).

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask app: `/signup` (Sema SDK), `/webhook` (Gemini + Resend) |
| `Dockerfile` | Container image for App Runner deployment |
| `.env.example` | Required environment variables |
| `requirements.txt` | Python dependencies |
| `Makefile` | `make install` / `make test` / `make run` |
| `tests/` | Pytest test suite |
