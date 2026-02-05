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
4. **Install deps**: `pip install -r requirements.txt`
5. **Run**: `python app.py`

### Webhook URL: Local vs Cloud

This app listens on `http://localhost:5050/webhook`.

| Your Setup | Webhook URL |
|------------|-------------|
| Sema running locally | `http://localhost:5050/webhook` (direct) |
| Sema cloud (api.withsema.com) | Use [ngrok](https://ngrok.com) or similar |

**For cloud Sema**, expose your local app first:

```bash
ngrok http 5050
# Use the https://xxx.ngrok.io/webhook URL in your inbox settings
```

### Local Docs Testing

To use local docs instead of deployed:

1. Run `make docs-serve` in the sema repo
2. Set `DOCS_CONTEXT_URL=http://127.0.0.1:8000/llm-context.json` in `.env`

## Ask a Question

Email your inbox address (e.g. `docs-qa@dev-in.withsema.com`) with:
- **Subject**: Your question
- **Body**: Additional context (optional)

You'll receive a reply from `docs-qa@out.withsema.com` (or your configured `RESEND_FROM_EMAIL`).

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask webhook receiver, OpenAI + Resend integration |
| `.env.example` | Required environment variables |
| `requirements.txt` | Python dependencies |
