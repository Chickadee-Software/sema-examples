# Docs Q&A Agent

Email a question about Sema docs → Get an answer via email.

## How It Works

```
Email question to docs inbox
       ↓
  Sema Inbox (e.g. docs-qa@dev-in.withsema.com)
       ↓
  ITEM_READY webhook
       ↓
  This App (verify signature, load llm-context.json)
       ↓
  OpenAI chat completions (docs as context)
       ↓
  Resend → Reply email to sender
```

## Setup

1. **Get a Sema inbox** with `email_enabled=True` and webhook URL pointing to this app
2. **Verify outbound domain** in Resend (`out.withsema.com` per [domains.md](../../sema/docs/infra/domains.md))
3. **Copy `.env.example` to `.env`** and fill in your values
4. **Install deps**: `make install`
5. **Run**: `make run`

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

### Local Docs Testing

To use local docs instead of deployed:

1. Run `mkdocs serve` in the sema repo (requires the `mkdocs-llm-context` plugin)
2. Set `DOCS_CONTEXT_URL=http://127.0.0.1:8000/llm-context.json` in `.env`

### Dev Mode: Query Without Email

Set `DEV_MODE=true` in `.env` to enable the `/ask` endpoint for local testing — no email required:

```bash
curl "http://localhost:5050/ask?q=How+do+I+set+up+an+inbox"
```

Returns the LLM answer as plain text. Never enable this in production.

## Ask a Question

Email your inbox address (e.g. `docs-qa@dev-in.withsema.com`) with:
- **Subject**: Your question
- **Body**: Additional context (optional)

You'll receive a reply from `docs-qa@out.withsema.com` (or your configured `RESEND_FROM_EMAIL`).

## Deployment

See [DEPLOY.md](DEPLOY.md) for AWS App Runner deployment instructions.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask webhook receiver, OpenAI + Resend integration |
| `Dockerfile` | Container image for App Runner deployment |
| `.env.example` | Required environment variables |
| `.env.deploy` | Deployment values (gitignored) |
| `requirements.txt` | Python dependencies |
| `Makefile` | `make install` / `make test` / `make run` |
| `tests/` | Pytest test suite |
