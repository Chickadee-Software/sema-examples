"""Tests for Beta Signup Inbox."""

import json
from unittest.mock import MagicMock, patch

import app as app_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_event(
    sender_address: str | None = "user@example.com",
    sender_display_name: str | None = "Jane Smith",
    subject: str | None = "I'd like API access",
):
    """Build a MagicMock that mimics a Sema webhook event."""
    content = MagicMock()
    content.subject = subject

    sender = MagicMock()
    sender.address = sender_address
    sender.display_name = sender_display_name

    deliverable = MagicMock()
    deliverable.content_summary = content
    deliverable.sender = sender if sender_address else None

    event = MagicMock()
    event.payload.deliverable = deliverable
    return event


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json == {"status": "ok"}


# ---------------------------------------------------------------------------
# compose_reply_html
# ---------------------------------------------------------------------------


def test_compose_reply_html_includes_calcom_link():
    result = app_module.compose_reply_html("Jane Smith", None)
    assert app_module.CALCOM_LINK in result
    assert "Jane" in result


def test_compose_reply_html_with_image():
    url = "https://example.com/image.png"
    result = app_module.compose_reply_html("Jane Smith", url)
    assert url in result
    assert "<img" in result


def test_compose_reply_html_without_image():
    result = app_module.compose_reply_html("Jane Smith", None)
    assert "<img" not in result


def test_compose_reply_html_no_sender_name():
    result = app_module.compose_reply_html(None, None)
    assert "there" in result


def test_compose_reply_html_escapes_xss():
    result = app_module.compose_reply_html("<script>alert(1)</script>", None)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_compose_reply_html_includes_signoff():
    result = app_module.compose_reply_html("Jane", None)
    assert "Alex Gibson" in result
    assert "withsema.com" in result


# ---------------------------------------------------------------------------
# generate_welcome_image
# ---------------------------------------------------------------------------


def test_generate_welcome_image_returns_none_when_disabled():
    with patch.object(app_module, "GENERATE_IMAGE", False):
        assert app_module.generate_welcome_image() is None


def test_generate_welcome_image_returns_url_on_success():
    mock_inline = MagicMock()
    mock_inline.data = b"fake-image-bytes"
    mock_inline.mime_type = "image/png"

    mock_part = MagicMock()
    mock_part.inline_data = mock_inline

    mock_response = MagicMock()
    mock_response.candidates = [MagicMock()]
    mock_response.candidates[0].content.parts = [mock_part]

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.return_value = mock_response

    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://s3.example.com/img.png"

    with (
        patch.object(app_module, "GENERATE_IMAGE", True),
        patch.object(app_module, "gemini_client", mock_gemini),
        patch.object(app_module, "s3_client", mock_s3),
        patch.object(app_module, "S3_BUCKET", "test-bucket"),
    ):
        url = app_module.generate_welcome_image()

    assert url == "https://s3.example.com/img.png"
    mock_s3.put_object.assert_called_once()
    mock_s3.generate_presigned_url.assert_called_once()


def test_generate_welcome_image_returns_none_on_error():
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = Exception("API error")

    with (
        patch.object(app_module, "GENERATE_IMAGE", True),
        patch.object(app_module, "gemini_client", mock_gemini),
        patch.object(app_module, "s3_client", MagicMock()),
        patch.object(app_module, "S3_BUCKET", "test-bucket"),
    ):
        assert app_module.generate_welcome_image() is None


# ---------------------------------------------------------------------------
# /signup endpoint
# ---------------------------------------------------------------------------


def test_signup_returns_400_when_no_email(client):
    resp = client.post("/signup", data=json.dumps({}), content_type="application/json")
    assert resp.status_code == 400
    assert resp.json["error"] == "Missing email"


def test_signup_returns_400_when_empty_email(client):
    resp = client.post(
        "/signup", data=json.dumps({"email": "  "}), content_type="application/json"
    )
    assert resp.status_code == 400
    assert resp.json["error"] == "Missing email"


def test_signup_returns_400_when_no_body(client):
    resp = client.post("/signup", content_type="application/json")
    assert resp.status_code == 400


def test_signup_success(client):
    with patch.object(app_module.sema_client, "upload_item") as mock_upload:
        resp = client.post(
            "/signup",
            data=json.dumps({"email": "user@example.com"}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    assert resp.json == {"ok": True}
    mock_upload.assert_called_once()
    call_kwargs = mock_upload.call_args
    assert call_kwargs[1]["sender_address"] == "user@example.com"
    assert call_kwargs[1]["inbox_id"] == app_module.SEMA_INBOX_ID


def test_signup_returns_500_on_sema_error(client):
    with patch.object(
        app_module.sema_client, "upload_item", side_effect=Exception("Sema down")
    ):
        resp = client.post(
            "/signup",
            data=json.dumps({"email": "user@example.com"}),
            content_type="application/json",
        )

    assert resp.status_code == 500
    assert resp.json["error"] == "Failed to submit signup"


# ---------------------------------------------------------------------------
# /webhook endpoint
# ---------------------------------------------------------------------------


def test_webhook_rejects_bad_signature(client):
    from sema_sdk import WebhookVerificationError

    with patch.object(
        app_module.verifier, "verify", side_effect=WebhookVerificationError("bad sig")
    ):
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
        patch.object(app_module, "generate_welcome_image", return_value=None),
        patch("resend.Emails.send") as mock_send,
    ):
        resp = client.post("/webhook", data=b"{}", content_type="application/json")

    assert resp.status_code == 200
    assert resp.json == {"ok": True}
    mock_send.assert_called_once()
    send_args = mock_send.call_args[0][0]
    assert send_args["to"] == ["user@example.com"]
    assert send_args["subject"] == "Re: I'd like API access"
    assert app_module.CALCOM_LINK in send_args["html"]


def test_webhook_success_with_image(client):
    event = make_mock_event()
    with (
        patch.object(app_module.verifier, "verify", return_value=event),
        patch.object(
            app_module,
            "generate_welcome_image",
            return_value="https://s3.example.com/img.png",
        ),
        patch("resend.Emails.send") as mock_send,
    ):
        resp = client.post("/webhook", data=b"{}", content_type="application/json")

    assert resp.status_code == 200
    send_args = mock_send.call_args[0][0]
    assert "https://s3.example.com/img.png" in send_args["html"]
    assert "<img" in send_args["html"]


def test_webhook_returns_200_even_on_resend_error(client):
    event = make_mock_event()
    with (
        patch.object(app_module.verifier, "verify", return_value=event),
        patch.object(app_module, "generate_welcome_image", return_value=None),
        patch("resend.Emails.send", side_effect=Exception("Resend down")),
    ):
        resp = client.post("/webhook", data=b"{}", content_type="application/json")

    assert resp.status_code == 200
    assert resp.json == {"ok": True}
