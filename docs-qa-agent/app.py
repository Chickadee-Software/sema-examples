"""Docs Q&A Agent - Email a question → Get an answer from Sema docs."""

import html
import os
import threading

import html2text
import httpx
import resend
from dotenv import load_dotenv
from flask import Flask, request
from openai import OpenAI
from sema_sdk import WebhookVerifier, WebhookVerificationError

_h2t = html2text.HTML2Text()
_h2t.body_width = 0

load_dotenv()

app = Flask(__name__)

DEV_MODE = os.environ.get("DEV_MODE", "").lower() == "true"

# Sema webhook verification
verifier = WebhookVerifier(secret=os.environ["SEMA_WEBHOOK_SECRET"])

# OpenAI client
openai_client = OpenAI()

# Resend
resend.api_key = os.environ["RESEND_API_KEY"]
RESEND_FROM_EMAIL = os.environ["RESEND_FROM_EMAIL"]
RESEND_REPLY_TO = os.environ.get("RESEND_REPLY_TO", "docs-qa@in.withsema.com")

# Docs context: fetch at startup, cache in memory
DOCS_CONTEXT_URL = os.environ.get(
    "DOCS_CONTEXT_URL", "https://docs.withsema.com/llm-context.json"
)


def load_docs_context() -> str:
    """Fetch docs JSON and format as context string for the LLM."""
    response = httpx.get(
        DOCS_CONTEXT_URL,
        headers={"User-Agent": "Sema-Docs-QA-Agent/1.0"},
    )
    response.raise_for_status()
    records = response.json()
    parts = []
    for r in records:
        parts.append(f"## {r['title']}\nURL: {r['url']}\n\n{r['content']}\n\n")
    return "\n".join(parts).strip()


_DOCS_CONTEXT: str | None = None


def get_docs_context() -> str:
    """Return cached docs context, loading on first call."""
    global _DOCS_CONTEXT
    if _DOCS_CONTEXT is None:
        _DOCS_CONTEXT = load_docs_context()
    return _DOCS_CONTEXT


def answer_question(question: str) -> str:
    """Send a question to OpenAI with docs context and return the answer."""
    docs = get_docs_context()
    system_prompt = (
        "You answer questions about Sema using only this documentation. "
        "Keep your answers brief, concise, focused, & precise. "
        "This reply will be sent as an email, so use plain text formatting only. "
        "Do NOT use markdown. For links, write the full URL inline (e.g., 'See: https://docs.withsema.com/api/webhooks/'). "
        "Use the full URL provided in each doc section, not relative paths. "
        "Include a source reference link to help the user. "
        "If unsure or the answer isn't in the docs, say so.\n\n"
        f"{docs}"
    )
    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )
    return completion.choices[0].message.content or ""


@app.route("/ask", methods=["GET"])
def ask():
    """Dev-only endpoint: answer a question directly without email. Requires DEV_MODE=true."""
    if not DEV_MODE:
        return {"error": "Not found"}, 404

    question = request.args.get("q", "").strip()
    if not question:
        return {"error": "Missing query parameter: q"}, 400

    try:
        answer = answer_question(question)
    except Exception as e:
        print(f"OpenAI error: {e}")
        return {"error": "Failed to get answer"}, 500

    return answer, 200, {"Content-Type": "text/plain; charset=utf-8"}


def process_and_reply(sender_addr: str, subject: str, question: str):
    """Background task: get answer from OpenAI and send reply via Resend."""
    try:
        answer = answer_question(question)
    except Exception as e:
        print(f"OpenAI error: {e}")
        return

    escaped = html.escape(answer)
    body_html_email = f"<pre style='white-space: pre-wrap; font-family: sans-serif;'>{escaped}</pre>"

    try:
        send_params: dict = {
            "from": RESEND_FROM_EMAIL,
            "to": [sender_addr],
            "subject": f"Re: {subject}",
            "html": body_html_email,
            "reply_to": RESEND_REPLY_TO,
        }
        resend.Emails.send(send_params)
        print(f"Replied to {sender_addr}")
    except Exception as e:
        print(f"Resend error: {e}")


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Receive Sema webhook, answer question from docs, reply via email."""
    try:
        event = verifier.verify(payload=request.data, headers=dict(request.headers))
    except WebhookVerificationError as e:
        print(f"Webhook verification failed: {e}")
        return {"error": str(e)}, 400

    deliverable = event.payload.deliverable
    content = deliverable.content_summary
    sender = deliverable.sender

    sender_addr = sender.address if sender else None
    if not sender_addr:
        print("No sender address in webhook")
        return {"error": "No sender address"}, 400

    subject = content.subject if content and content.subject else "Question"
    body_html = content.body_html if content else ""
    body_text = _h2t.handle(body_html).strip() if body_html else ""
    if content and not body_text and content.body_preview:
        body_text = content.body_preview

    question = f"{subject}\n\n{body_text}".strip()
    if not question:
        print("Empty question")
        return {"error": "Empty question"}, 400

    # Process in background to respond immediately and avoid webhook retries
    thread = threading.Thread(
        target=process_and_reply,
        args=(sender_addr, subject, question),
    )
    thread.start()

    return {"ok": True}, 200


if __name__ == "__main__":
    print("Starting Docs Q&A Agent on http://localhost:5050/webhook")
    app.run(port=5050, debug=True)
