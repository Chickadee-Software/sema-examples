"""Tests for Docs Q&A Agent."""

from unittest.mock import MagicMock, patch

import pytest

import app as app_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DOCS = [
    {"title": "Getting Started", "url": "https://docs.example.com/start/", "content": "How to get started."},
    {"title": "API Reference", "url": "https://docs.example.com/api/", "content": "API details here."},
]

EXPECTED_CONTEXT = (
    "## Getting Started\nURL: https://docs.example.com/start/\n\nHow to get started.\n\n"
    "\n"
    "## API Reference\nURL: https://docs.example.com/api/\n\nAPI details here.\n\n"
).strip()


def make_mock_event(
    sender_address: str | None = "user@example.com",
    subject: str | None = "How do I set up an inbox?",
    body_html: str = "<p>Please help.</p>",
    body_preview: str = "",
):
    """Build a MagicMock that mimics a Sema webhook event."""
    content = MagicMock()
    content.subject = subject
    content.body_html = body_html
    content.body_preview = body_preview

    sender = MagicMock()
    sender.address = sender_address

    deliverable = MagicMock()
    deliverable.content_summary = content
    deliverable.sender = sender if sender_address else None

    event = MagicMock()
    event.payload.deliverable = deliverable
    return event


def mock_httpx_get(records: list = SAMPLE_DOCS):
    """Return a mock httpx response with the given records."""
    response = MagicMock()
    response.json.return_value = records
    return response


def mock_openai_completion(answer: str = "Here is your answer."):
    """Return a mock OpenAI completion response."""
    choice = MagicMock()
    choice.message.content = answer
    completion = MagicMock()
    completion.choices = [choice]
    return completion


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json == {"status": "ok"}


# ---------------------------------------------------------------------------
# load_docs_context
# ---------------------------------------------------------------------------


def test_load_docs_context_formats_records():
    with patch("httpx.get", return_value=mock_httpx_get()) as mock_get:
        result = app_module.load_docs_context()

    mock_get.assert_called_once()
    assert "## Getting Started" in result
    assert "URL: https://docs.example.com/start/" in result
    assert "How to get started." in result
    assert "## API Reference" in result


def test_load_docs_context_raises_on_http_error():
    response = MagicMock()
    response.raise_for_status.side_effect = Exception("404 Not Found")
    with patch("httpx.get", return_value=response):
        with pytest.raises(Exception, match="404 Not Found"):
            app_module.load_docs_context()


def test_get_docs_context_caches_result():
    with patch("httpx.get", return_value=mock_httpx_get()) as mock_get:
        first = app_module.get_docs_context()
        second = app_module.get_docs_context()

    assert first == second
    mock_get.assert_called_once()  # only fetched once


# ---------------------------------------------------------------------------
# /ask endpoint
# ---------------------------------------------------------------------------


def test_ask_returns_404_when_dev_mode_off(client):
    with patch.object(app_module, "DEV_MODE", False):
        resp = client.get("/ask?q=hello")
    assert resp.status_code == 404


def test_ask_returns_400_when_no_question(client):
    with patch.object(app_module, "DEV_MODE", True):
        resp = client.get("/ask")
    assert resp.status_code == 400
    assert b"Missing query parameter" in resp.data


def test_ask_returns_answer(client):
    with (
        patch.object(app_module, "DEV_MODE", True),
        patch("httpx.get", return_value=mock_httpx_get()),
        patch.object(
            app_module.openai_client.chat.completions,
            "create",
            return_value=mock_openai_completion("Set up an inbox via the dashboard."),
        ),
    ):
        resp = client.get("/ask?q=How+do+I+set+up+an+inbox")

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/plain")
    assert b"Set up an inbox via the dashboard." in resp.data


def test_ask_returns_500_on_openai_error(client):
    with (
        patch.object(app_module, "DEV_MODE", True),
        patch("httpx.get", return_value=mock_httpx_get()),
        patch.object(
            app_module.openai_client.chat.completions,
            "create",
            side_effect=Exception("OpenAI unavailable"),
        ),
    ):
        resp = client.get("/ask?q=hello")

    assert resp.status_code == 500
    assert b"Failed to get answer" in resp.data


# ---------------------------------------------------------------------------
# /webhook endpoint
# ---------------------------------------------------------------------------


def test_webhook_rejects_bad_signature(client):
    from sema_sdk import WebhookVerificationError

    with patch.object(app_module.verifier, "verify", side_effect=WebhookVerificationError("bad sig")):
        resp = client.post("/webhook", data=b"{}", content_type="application/json")

    assert resp.status_code == 400
    assert b"bad sig" in resp.data


def test_webhook_returns_400_when_no_sender(client):
    event = make_mock_event(sender_address=None)
    with patch.object(app_module.verifier, "verify", return_value=event):
        resp = client.post("/webhook", data=b"{}", content_type="application/json")

    assert resp.status_code == 400
    assert b"No sender address" in resp.data


def test_webhook_success(client):
    event = make_mock_event()
    with (
        patch.object(app_module.verifier, "verify", return_value=event),
        patch("httpx.get", return_value=mock_httpx_get()),
        patch.object(
            app_module.openai_client.chat.completions,
            "create",
            return_value=mock_openai_completion("Here is the answer."),
        ),
        patch("resend.Emails.send") as mock_send,
    ):
        resp = client.post("/webhook", data=b"{}", content_type="application/json")

    assert resp.status_code == 200
    assert resp.json == {"ok": True}
    mock_send.assert_called_once()
    send_args = mock_send.call_args[0][0]
    assert send_args["to"] == ["user@example.com"]
    assert send_args["subject"] == "Re: How do I set up an inbox?"
    assert "Here is the answer." in send_args["html"]


def test_webhook_returns_200_even_on_openai_error(client):
    """Webhook returns 200 immediately; OpenAI errors are logged but don't block response."""
    event = make_mock_event()
    with (
        patch.object(app_module.verifier, "verify", return_value=event),
        patch("httpx.get", return_value=mock_httpx_get()),
        patch.object(
            app_module.openai_client.chat.completions,
            "create",
            side_effect=Exception("OpenAI down"),
        ),
    ):
        resp = client.post("/webhook", data=b"{}", content_type="application/json")

    assert resp.status_code == 200
    assert resp.json == {"ok": True}


def test_webhook_returns_200_even_on_resend_error(client):
    """Webhook returns 200 immediately; Resend errors are logged but don't block response."""
    event = make_mock_event()
    with (
        patch.object(app_module.verifier, "verify", return_value=event),
        patch("httpx.get", return_value=mock_httpx_get()),
        patch.object(
            app_module.openai_client.chat.completions,
            "create",
            return_value=mock_openai_completion(),
        ),
        patch("resend.Emails.send", side_effect=Exception("Resend down")),
    ):
        resp = client.post("/webhook", data=b"{}", content_type="application/json")

    assert resp.status_code == 200
    assert resp.json == {"ok": True}
