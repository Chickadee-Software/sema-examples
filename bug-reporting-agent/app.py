"""Bug Reporting Agent - User emails bug report → Create Linear issue."""

import os

import html2text
import httpx
from dotenv import load_dotenv
from flask import Flask, request

from sema_sdk import (
    SemaClient,
    WebhookVerifier,
    WebhookVerificationError,
    partition_email_attachments,
    resolve_email_inline_images,
)

# Configure html2text for clean markdown output
_h2t = html2text.HTML2Text()
_h2t.body_width = 0  # Don't wrap lines

load_dotenv()

app = Flask(__name__)

# Sema webhook verification and API client
verifier = WebhookVerifier(secret=os.environ["SEMA_WEBHOOK_SECRET"])
sema_client = SemaClient() if os.environ.get("SEMA_API_KEY") else None
if not sema_client:
    print("WARNING: SEMA_API_KEY not set - attachment downloads will be disabled")

# Linear API
LINEAR_API_KEY = os.environ["LINEAR_API_KEY"]
LINEAR_TEAM_ID = os.environ["LINEAR_TEAM_ID"]


class LinearError(Exception):
    """Error from Linear API."""
    pass


def create_linear_issue(title: str, description: str) -> tuple[str, str]:
    """Create an issue in Linear. Returns (identifier, url)."""
    query = """
        mutation CreateIssue($title: String!, $description: String!, $teamId: String!) {
            issueCreate(input: { title: $title, description: $description, teamId: $teamId }) {
                success
                issue { id identifier url }
            }
        }
    """
    variables = {
        "title": title,
        "description": description,
        "teamId": LINEAR_TEAM_ID,
    }
    response = httpx.post(
        "https://api.linear.app/graphql",
        json={"query": query, "variables": variables},
        headers={"Authorization": LINEAR_API_KEY, "Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()

    # GraphQL can return 200 with errors in the response
    if "errors" in data:
        raise LinearError(data["errors"][0].get("message", "Unknown error"))

    issue = data["data"]["issueCreate"]["issue"]
    return issue["identifier"], issue["url"]


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Receive Sema webhook, create Linear issue."""
    # Verify the webhook signature
    try:
        event = verifier.verify(payload=request.data, headers=dict(request.headers))
    except WebhookVerificationError as e:
        print(f"Webhook verification failed: {e}")
        print(f"Headers: {dict(request.headers)}")
        print(f"Payload: {request.data[:500]}")  # First 500 bytes
        return {"error": str(e)}, 400

    # Extract from the webhook payload structure
    deliverable = event.payload.deliverable
    item_id = event.payload.item_id
    content = deliverable.content_summary
    sender = deliverable.sender

    # Build issue title
    title = content.subject if content and content.subject else "Bug Report"

    # Fetch attachments with presigned URLs (needed for images)
    attachments = []
    if sema_client and deliverable.attachments:
        try:
            attachments = sema_client.get_item_attachments(item_id).attachments
        except Exception as e:
            print(f"Failed to fetch attachments: {e}")

    # Build issue description
    sender_addr = sender.address if sender else "unknown"
    description = f"**Reported by:** {sender_addr}\n\n"

    # Prefer body_html with resolved inline images, fall back to body_preview
    body_html = content.body_html if content else ""
    if body_html:
        resolved_html = resolve_email_inline_images(body_html, attachments)
        description += _h2t.handle(resolved_html).strip()
    elif content and content.body_preview:
        description += content.body_preview

    # Partition attachments: inline (embedded in HTML) vs non-inline (list separately)
    _, non_inline = partition_email_attachments(body_html, attachments)
    if non_inline:
        description += "\n\n**Attachments:**\n"
        for att in non_inline:
            if att.download_url:
                # Images: use ![](url) so Linear displays them
                if att.content_type.startswith("image/"):
                    description += f"![{att.filename}]({att.download_url})\n"
                else:
                    description += f"- [{att.filename}]({att.download_url}) ({att.content_type})\n"
            else:
                description += f"- {att.filename} ({att.content_type})\n"

    # Create the Linear issue
    try:
        issue_id, issue_url = create_linear_issue(title, description)
    except (LinearError, httpx.HTTPError) as e:
        print(f"Failed to create Linear issue: {e}")
        return {"error": "Failed to create issue"}, 500

    print(f"Created Linear issue: {issue_id} → {issue_url}")
    return {"ok": True, "issue": issue_id}, 200


if __name__ == "__main__":
    print("Starting Bug Reporting Agent on http://localhost:5050/webhook")
    app.run(port=5050, debug=True)
