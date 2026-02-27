"""Beta Signup Inbox - Welcome new beta signups with a personalized reply + AI-generated image."""

import html
import io
import os
import threading
import uuid

import boto3
import resend
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types
from sema_sdk import SemaClient, WebhookVerifier, WebhookVerificationError

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/signup": {"origins": "*"}})

DEV_MODE = os.environ.get("DEV_MODE", "").lower() == "true"

verifier = WebhookVerifier(secret=os.environ["SEMA_WEBHOOK_SECRET"])

sema_client = SemaClient(
    api_key=os.environ["SEMA_API_KEY"],
    base_url=os.environ.get("SEMA_BASE_URL", "https://dev-api.withsema.com"),
)
SEMA_INBOX_ID = os.environ["SEMA_INBOX_ID"]

resend.api_key = os.environ["RESEND_API_KEY"]
RESEND_FROM_EMAIL = os.environ["RESEND_FROM_EMAIL"]
RESEND_REPLY_TO = os.environ.get("RESEND_REPLY_TO", "beta@dev-in.withsema.com")

CALCOM_LINK = os.environ.get(
    "CALCOM_LINK", "https://cal.com/alex-gibson/sema-beta-access"
)

GENERATE_IMAGE = os.environ.get("GENERATE_IMAGE", "").lower() == "true"
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "beta-welcome")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
PRESIGNED_URL_EXPIRY = 30 * 24 * 60 * 60  # 30 days

gemini_client = None
s3_client = None
if GENERATE_IMAGE:
    gemini_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    s3_client = boto3.client("s3", region_name=S3_REGION)


def generate_welcome_image() -> str | None:
    """Generate a welcome image via Gemini and upload to S3. Returns a presigned URL."""
    if not GENERATE_IMAGE or not gemini_client or not s3_client:
        return None

    prompt = (
        "Create a beautiful, abstract wide landscape banner graphic. "
        "Brand palette: sky blue (#7dd3fc), soft violet (#c4b5fd), golden yellow (#FFC947) "
        "as a small accent, on a deep dark blue-gray background (#152836). "
        "Depict stylized signal streams or light trails converging toward a glowing "
        "central point — like messages flowing into an inbox and emerging as clean, "
        "structured beams. Minimal, geometric, tech-forward. "
        "No text, no letters, no words in the image."
    )

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["Image"]),
        )

        image_bytes = None
        mime_type = "image/png"
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                image_bytes = part.inline_data.data
                mime_type = getattr(part.inline_data, "mime_type", mime_type)
                break

        if not image_bytes:
            print("No image data in Gemini response", flush=True)
            return None

        image_key = f"{S3_PREFIX}/{uuid.uuid4().hex}.png"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=image_key,
            Body=image_bytes,
            ContentType=mime_type,
        )

        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": image_key},
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )
    except Exception as e:
        print(f"Image generation error: {e}", flush=True)
        return None


def compose_reply_html(sender_name: str | None, image_url: str | None) -> str:
    """Build the HTML email body."""
    name = sender_name.split()[0] if sender_name else "there"
    escaped_name = html.escape(name)

    image_block = ""
    if image_url:
        image_block = (
            f'<img src="{html.escape(image_url)}" alt="Welcome to Sema" '
            f'style="width:100%;max-width:600px;border-radius:8px;margin-bottom:24px;" />'
        )

    return f"""\
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;color:#1a1a2e;">
  {image_block}
  <p style="font-size:18px;margin-bottom:16px;">Hey {escaped_name},</p>
  <p style="font-size:15px;line-height:1.6;margin-top:24px;">Thank you for requesting access to the Sema beta. Book a quick 15 minutes with our founder Alex to get you up-and-running:</p>
  <p style="margin:16px 0;">
    <a href="{CALCOM_LINK}"
       style="display:inline-block;background:linear-gradient(135deg,#7dd3fc,#c4b5fd);color:#0f172a;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:600;font-size:15px;">
      Schedule a Call &#8594;
    </a>
  </p>
  <p style="font-size:13px;color:#666;margin-top:8px;"><a href="{CALCOM_LINK}" style="color:#666;">{CALCOM_LINK}</a></p>
  <p style="font-size:15px;margin-top:24px;">Talk soon,<br/>Alex Gibson<br/><a href="https://withsema.com" style="color:#7dd3fc;text-decoration:none;">withsema.com</a></p>
</div>"""


def process_and_reply(sender_addr: str, sender_name: str | None, subject: str):
    """Background task: generate welcome image and send reply via Resend."""
    image_url = generate_welcome_image()
    body_html = compose_reply_html(sender_name, image_url)

    try:
        resend.Emails.send(
            {
                "from": RESEND_FROM_EMAIL,
                "to": [sender_addr],
                "subject": f"Re: {subject}",
                "html": body_html,
                "reply_to": RESEND_REPLY_TO,
            }
        )
        print(f"Replied to {sender_addr}", flush=True)
    except Exception as e:
        print(f"Resend error: {e}", flush=True)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for load balancers and container orchestration."""
    return {"status": "ok"}, 200


@app.route("/signup", methods=["POST"])
def signup():
    """Accept a beta signup email and submit it to the Sema inbox."""
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"error": "Missing email"}), 400

    try:
        body = f"Beta signup request from landing page at {uuid.uuid4().hex}"
        result = sema_client.upload_item(
            inbox_id=SEMA_INBOX_ID,
            file=io.BytesIO(body.encode()),
            sender_address=email,
            subject="I'd like API access",
            content_type="text/plain",
        )
        print(f"Signup uploaded: id={result.id} status={result.status} duplicate={result.is_duplicate} email={email}", flush=True)
    except Exception as e:
        print(f"Sema API error: {e}", flush=True)
        return jsonify({"error": "Failed to submit signup"}), 500

    return jsonify({"ok": True}), 200


@app.route("/test", methods=["GET"])
def test_signup():
    """Dev-only: trigger the full flow for a given email. Requires DEV_MODE=true.

    Usage: GET /test?email=you@example.com&name=Jane&subject=Hello
    """
    if not DEV_MODE:
        return {"error": "Not found"}, 404

    email = request.args.get("email", "").strip()
    if not email:
        return {"error": "Missing query parameter: email"}, 400

    name = request.args.get("name") or None
    subject = request.args.get("subject", "I'd like API access")

    process_and_reply(email, name, subject)
    return {"ok": True, "sent_to": email}, 200


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Receive Sema webhook and reply with a personalized welcome email."""
    try:
        event = verifier.verify(payload=request.data, headers=dict(request.headers))
    except WebhookVerificationError as e:
        print(f"Webhook verification failed: {e}", flush=True)
        return {"error": str(e)}, 400

    deliverable = event.payload.deliverable
    sender = deliverable.sender
    content = deliverable.content_summary

    sender_addr = sender.address if sender else None
    if not sender_addr:
        print("No sender address in webhook", flush=True)
        return {"error": "No sender address"}, 400

    sender_name = sender.display_name if sender else None
    subject = content.subject if content and content.subject else "Beta Access"

    thread = threading.Thread(
        target=process_and_reply,
        args=(sender_addr, sender_name, subject),
    )
    thread.start()

    return {"ok": True}, 200


if __name__ == "__main__":
    print("Starting Beta Signup Inbox on http://localhost:5050/webhook")
    app.run(port=5050, debug=True)
