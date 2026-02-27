"""Pytest configuration: set required env vars before importing app."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SEMA_WEBHOOK_SECRET", "whsec_test")
os.environ.setdefault("SEMA_API_KEY", "sema_test")
os.environ.setdefault("SEMA_INBOX_ID", "test-inbox-id")
os.environ.setdefault("RESEND_API_KEY", "re_test")
os.environ.setdefault("RESEND_FROM_EMAIL", "test@example.com")

import pytest

from app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
