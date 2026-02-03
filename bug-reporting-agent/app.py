"""Bug Reporting Agent - Email bug reports → Linear issues."""

import os

import httpx
from dotenv import load_dotenv
from flask import Flask, request

from sema_sdk import WebhookVerifier, WebhookVerificationError

load_dotenv()

app = Flask(__name__)

# Sema webhook verification
verifier = WebhookVerifier(secret=os.environ["SEMA_WEBHOOK_SECRET"])

# Linear API
LINEAR_API_KEY = os.environ["LINEAR_API_KEY"]
LINEAR_TEAM_ID = os.environ["LINEAR_TEAM_ID"]
LINEAR_BUG_LABEL_ID = os.environ.get("LINEAR_BUG_LABEL_ID")  # Optional


class LinearError(Exception):
    """Error from Linear API."""
    pass


def create_linear_issue(title: str, description: str) -> tuple[str, str]:
    """Create an issue in Linear. Returns (identifier, url)."""
    query = """
        mutation CreateIssue($title: String!, $description: String!, $teamId: String!, $labelIds: [String!]) {
            issueCreate(input: { title: $title, description: $description, teamId: $teamId, labelIds: $labelIds }) {
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
    if LINEAR_BUG_LABEL_ID:
        variables["labelIds"] = [LINEAR_BUG_LABEL_ID]
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
        return {"error": str(e)}, 400

    # Extract from the webhook payload structure
    deliverable = event.payload.deliverable
    content = deliverable.content_summary
    sender = deliverable.sender

    # Build issue title
    title = content.subject if content and content.subject else "Bug Report"

    # Build issue description
    sender_addr = sender.address if sender else "unknown"
    description = f"**Reported by:** {sender_addr}\n\n"
    
    if content and content.body_preview:
        description += content.body_preview

    # Note attachments if present
    if deliverable.attachments:
        description += "\n\n**Attachments:**\n"
        for att in deliverable.attachments:
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
