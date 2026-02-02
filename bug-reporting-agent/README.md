# Bug Reporting Agent

Make it easy for users to report bugs. Email a bug report → Get a Linear issue.

## How It Works

```
Screenshot + Email
       ↓
  Sema Inbox (report-bugs@dev-in.withsema.com)
       ↓
  [DKIM/SPF verify, MIME parse, extract attachment]
       ↓
  Structured Webhook Payload
       ↓
  This App (verify signature, extract fields)
       ↓
  Linear API → Issue Created
```

## Setup

1. **Get a Sema inbox** with a webhook URL pointing to this app
2. **Get a Linear API key** from Linear settings
3. **Copy `.env.example` to `.env`** and fill in your values
4. **Install deps**: `pip install -r requirements.txt`
5. **Run**: `python app.py`

## Send a Bug Report

Email `report-bugs@dev-in.withsema.com` with:
- **Subject**: Bug title (becomes Linear issue title)
- **Body**: Bug description (becomes issue description)
- **Attachment**: Screenshot (optional, linked in issue)

Watch the Linear issue appear.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask webhook receiver + Linear integration |
| `.env.example` | Required environment variables |
| `requirements.txt` | Python dependencies |
