"""Pytest configuration: set required env vars before importing app."""

import os

os.environ.setdefault("SEMA_WEBHOOK_SECRET", "whsec_test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("RESEND_API_KEY", "re_test")
os.environ.setdefault("RESEND_FROM_EMAIL", "test@example.com")

import pytest

import app as app_module
from app import app as flask_app


@pytest.fixture(autouse=True)
def reset_docs_cache():
    """Reset the in-memory docs context cache between tests."""
    app_module._DOCS_CONTEXT = None
    yield
    app_module._DOCS_CONTEXT = None


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
