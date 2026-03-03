"""Clinical signal detection — domain-specific, rule-based.

This is NOT part of Sema (which handles general PII detection).
Clinical signal detection is healthcare business logic — it belongs
in the application layer, not the infrastructure layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ClinicalSignal:
    """A detected clinical signal in the input text."""

    type: str
    term: str
    context: str


SIGNAL_PATTERNS: dict[str, list[str]] = {
    "symptom": [
        "chest pain",
        "shortness of breath",
        "dizziness",
        "headache",
        "nausea",
        "fatigue",
        "palpitations",
        "swelling",
        "blurred vision",
        "numbness",
    ],
    "medication": [
        "Lisinopril",
        "Metformin",
        "Atorvastatin",
        "Amlodipine",
        "Omeprazole",
        "Metoprolol",
        "Losartan",
        "Levothyroxine",
        "Warfarin",
        "Insulin",
    ],
    "risk_signal": [
        "skipping",
        "stopped taking",
        "non-adherent",
        "missed doses",
        "not taking",
        "ran out of",
        "can't afford",
        "refusing",
        "discontinued",
    ],
    "condition": [
        "diabetes",
        "hypertension",
        "cardiac",
        "stroke",
        "renal failure",
        "COPD",
        "asthma",
        "seizure",
        "arrhythmia",
    ],
}

_COMPILED_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    signal_type: [(term, re.compile(re.escape(term), re.IGNORECASE)) for term in terms]
    for signal_type, terms in SIGNAL_PATTERNS.items()
}


def detect_clinical_signals(text: str) -> list[ClinicalSignal]:
    """Scan text for clinical signals. Returns all matches."""
    signals: list[ClinicalSignal] = []
    for signal_type, patterns in _COMPILED_PATTERNS.items():
        for term, pattern in patterns:
            match = pattern.search(text)
            if match:
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                context = text[start:end].strip()
                signals.append(ClinicalSignal(type=signal_type, term=term, context=context))
    return signals


DECISION_SUPPORT_RESPONSE = (
    "Clinical alert: Patient reports symptoms concurrent with medication "
    "non-adherence. Recommend provider review prior to scheduled visit. "
    "Flag for clinical decision support."
)
