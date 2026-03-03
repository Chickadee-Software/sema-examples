"""Webhook listener and pipeline orchestration.

Receives ITEM_READY webhooks from Sema, extracts PII enrichment,
dispatches to classifier and interceptor in parallel, and streams
events to the CLI via a shared queue.
"""

from __future__ import annotations

import queue
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from flask import Flask, request
from openai import OpenAI
from sema_sdk import WebhookVerifier, WebhookVerificationError

from agents import classify
from interceptor import DECISION_SUPPORT_RESPONSE, detect_clinical_signals


@dataclass(frozen=True)
class PipelineEvent:
    """An event pushed from the pipeline to the CLI for rendering."""

    stage: str
    data: dict[str, Any] = field(default_factory=dict)
    elapsed: float = 0.0


app = Flask(__name__)

event_queue: queue.Queue[PipelineEvent] = queue.Queue()

_openai_client: OpenAI | None = None
_verifier: WebhookVerifier | None = None


def init(webhook_secret: str, openai_api_key: str) -> None:
    """Initialize the pipeline (called from cli.py before starting Flask)."""
    global _openai_client, _verifier
    _verifier = WebhookVerifier(secret=webhook_secret)
    _openai_client = OpenAI(api_key=openai_api_key)


def _emit(stage: str, start_time: float, **data: Any) -> None:
    event_queue.put(PipelineEvent(stage=stage, data=data, elapsed=time.time() - start_time))


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}, 200


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Receive Sema ITEM_READY webhook and run the pipeline."""
    pipeline_start = time.time()

    try:
        event = _verifier.verify(payload=request.data, headers=dict(request.headers))
    except WebhookVerificationError as e:
        return {"error": str(e)}, 400

    _emit("webhook_received", pipeline_start, item_id=event.payload.item_id)

    deliverable = event.payload.deliverable
    enrichment = getattr(deliverable, "enrichment", None) or {}
    pii_step = enrichment.get("steps", {}).get("pii_detect", {}) if enrichment else {}

    pii_detected = pii_step.get("pii_detected", False)
    risk_level = pii_step.get("risk_level", "none")
    entity_count = pii_step.get("entity_count", 0)
    by_type = pii_step.get("by_type", {})

    _emit(
        "pii_result",
        pipeline_start,
        pii_detected=pii_detected,
        risk_level=risk_level,
        entity_count=entity_count,
        by_type=by_type,
    )

    content = deliverable.content_summary
    query_text = ""
    if content:
        subject = content.subject or ""
        body = content.body_preview or ""
        query_text = f"{subject}\n{body}".strip() if subject and body else (subject or body)

    if not query_text:
        _emit("error", pipeline_start, message="No query text found in webhook payload")
        return {"error": "No query text"}, 400

    def run_classifier() -> dict[str, Any]:
        _emit("classifier_started", pipeline_start)
        decision, response = classify(
            query_text, pii_detected=pii_detected, openai_client=_openai_client
        )
        result = {
            "agent": decision.agent,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
            "did_fallback": decision.did_fallback,
            "pii_filtered": pii_detected,
            "response": response,
        }
        _emit("classifier_result", pipeline_start, **result)
        return result

    def run_interceptor() -> dict[str, Any]:
        _emit("interceptor_started", pipeline_start)
        signals = detect_clinical_signals(query_text)
        has_signals = len(signals) > 0
        result = {
            "signals": [
                {"type": s.type, "term": s.term, "context": s.context} for s in signals
            ],
            "clinical_alert": has_signals,
            "routed_to": "decision_support" if has_signals else None,
            "response": DECISION_SUPPORT_RESPONSE if has_signals else None,
        }
        _emit("interceptor_result", pipeline_start, **result)
        return result

    classifier_result = {}
    interceptor_result = {}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(run_classifier): "classifier",
            pool.submit(run_interceptor): "interceptor",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                if name == "classifier":
                    classifier_result = future.result()
                else:
                    interceptor_result = future.result()
            except Exception as e:
                _emit("error", pipeline_start, source=name, message=str(e))

    _emit(
        "aggregated",
        pipeline_start,
        classifier=classifier_result,
        interceptor=interceptor_result,
        query=query_text,
        pii_detected=pii_detected,
        risk_level=risk_level,
    )

    return {"ok": True}, 200
