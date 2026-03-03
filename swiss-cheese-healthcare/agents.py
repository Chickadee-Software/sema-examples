"""Agent registry, PII-aware filtering, and OpenAI-based classification.

Uses agent-registry-router for structured classify -> validate -> dispatch.
PII-aware routing is implemented here as a filtered-registry pattern —
not forked into the library, because PII policy is application-level concern.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from agent_registry_router import (
    AgentRegistration,
    AgentRegistry,
    RouteDecision,
    ValidatedRouteDecision,
    build_classifier_system_prompt,
    validate_route_decision,
)

AGENT_CONFIGS: list[dict[str, Any]] = [
    {
        "name": "receptionist",
        "description": (
            "Executes appointment actions: booking, rescheduling, cancelling, "
            "and follow-up scheduling. Requires specific patient details to act. "
            "Do NOT route here for general questions about how booking works."
        ),
        "handles_pii": True,
        "routable": True,
    },
    {
        "name": "general",
        "description": (
            "Answers informational questions about the clinic — how to book "
            "appointments, office hours, location, policies, procedures, insurance, "
            "and how things work. Route here when the user is asking a question, "
            "not requesting an action."
        ),
        "handles_pii": False,
        "routable": True,
    },
    {
        "name": "billing",
        "description": (
            "Handles billing actions and account-specific inquiries: outstanding "
            "balances, payment processing, insurance claim disputes, and refunds."
        ),
        "handles_pii": True,
        "routable": True,
    },
    {
        "name": "decision_support",
        "description": (
            "Clinical decision support for providers. Reviews medication, "
            "symptoms, and risk factors."
        ),
        "handles_pii": True,
        "routable": False,
    },
]

PII_SAFE_AGENTS: set[str] = {
    cfg["name"] for cfg in AGENT_CONFIGS if cfg["handles_pii"]
}

MOCK_RESPONSES: dict[str, str] = {
    "receptionist": (
        "Appointment request received. Pulling up patient record to confirm "
        "scheduling and provider availability."
    ),
    "billing": (
        "Your billing inquiry has been received. A billing specialist will review "
        "your account and follow up within 1 business day."
    ),
    "decision_support": (
        "Clinical alert: Patient reports symptoms concurrent with medication "
        "non-adherence. Recommend provider review prior to scheduled visit."
    ),
}

_CLINIC_DOCS: str | None = None


def _load_clinic_docs() -> str:
    global _CLINIC_DOCS
    if _CLINIC_DOCS is None:
        path = Path(__file__).parent / "clinic_policies.md"
        _CLINIC_DOCS = path.read_text()
    return _CLINIC_DOCS


def _answer_from_docs(query: str, openai_client: OpenAI) -> str:
    """Generate a contextual answer using clinic documentation."""
    docs = _load_clinic_docs()
    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful clinic assistant. Answer the patient's question "
                    "using only the clinic documentation below. Be brief and direct — "
                    "2-3 sentences max. If the answer isn't in the docs, say so.\n\n"
                    f"{docs}"
                ),
            },
            {"role": "user", "content": query},
        ],
    )
    return completion.choices[0].message.content or "I couldn't find that information."


def build_full_registry() -> AgentRegistry:
    """Build the complete agent registry from configs."""
    registry = AgentRegistry()
    for cfg in AGENT_CONFIGS:
        registry.register(
            AgentRegistration(
                name=cfg["name"],
                description=cfg["description"],
                routable=cfg["routable"],
            )
        )
    return registry


def build_pii_filtered_registry() -> AgentRegistry:
    """Build a registry containing only PII-safe, routable agents."""
    registry = AgentRegistry()
    for cfg in AGENT_CONFIGS:
        if cfg["handles_pii"] and cfg["routable"]:
            registry.register(
                AgentRegistration(
                    name=cfg["name"],
                    description=cfg["description"],
                    routable=True,
                )
            )
    return registry


_CLASSIFIER_EXTRA_INSTRUCTIONS = (
    "You are classifying healthcare queries for a medical clinic. "
    "Consider the patient's intent: are they asking a general question, "
    "scheduling something, or asking about billing? "
    "Respond with valid JSON: {\"agent\": \"<name>\", \"confidence\": <0.0-1.0>, \"reasoning\": \"<why>\"}."
)


def classify(
    query: str,
    *,
    pii_detected: bool,
    openai_client: OpenAI,
) -> tuple[ValidatedRouteDecision, str]:
    """Classify a query and return the validated decision + agent response.

    When PII is detected, the classifier only sees PII-safe agents.
    """
    if pii_detected:
        registry = build_pii_filtered_registry()
        default = "receptionist"
    else:
        registry = build_full_registry()
        default = "general"

    system_prompt = build_classifier_system_prompt(
        registry,
        default_agent=default,
        extra_instructions=_CLASSIFIER_EXTRA_INSTRUCTIONS,
    )

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    decision = RouteDecision(
        agent=parsed.get("agent", default),
        confidence=float(parsed.get("confidence", 0.5)),
        reasoning=parsed.get("reasoning"),
    )

    validated = validate_route_decision(
        decision,
        registry=registry,
        default_agent=default,
        allow_fallback=True,
    )

    if validated.agent == "general":
        response = _answer_from_docs(query, openai_client)
    else:
        response = MOCK_RESPONSES.get(validated.agent, f"[{validated.agent}] handled the query.")
    return validated, response
