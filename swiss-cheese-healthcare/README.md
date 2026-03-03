# Swiss Cheese Healthcare Demo

A working prototype demonstrating layered safety for healthcare AI agent routing — inspired by the [Swiss Cheese Model](https://en.wikipedia.org/wiki/Swiss_cheese_model) of risk management.

## Problem

Healthcare AI systems must handle three concerns simultaneously:

1. **PII detection** — Is there personally identifiable information? (General infrastructure problem)
2. **Access control** — Which agents are authorized to handle PII? (Security/policy problem)
3. **Clinical signal detection** — Does the content contain clinical details that need specialist routing? (Domain-specific problem)

No single layer catches everything. Stack them, and the holes stop aligning.

## Architecture

```
Healthcare query
       │
       ▼
   ┌────────┐
   │  Sema   │  PII detection (Presidio)
   └───┬────┘  General-purpose — works for any industry
       │
       │  ITEM_READY webhook
       ▼
 ┌────────────┐
 │  Webhook    │  Verify signature, extract PII + content
 │  Listener   │
 └──┬──────┬──┘
    │      │  parallel dispatch
    ▼      ▼
┌────────┐ ┌──────────────┐
│Classif.│ │ Interceptor  │
│(ARR)   │ │ (rules)      │
│        │ │              │
│PII-safe│ │Clinical      │
│agent   │ │signal        │
│routing │ │detection     │
└───┬────┘ └──────┬───────┘
    │              │
    ▼              ▼
  ┌──────────────────┐
  │    Aggregator     │
  │  Wait for both,   │
  │  merge results    │
  └────────┬─────────┘
           ▼
     CLI Output
```

**Key architectural insight:** PII detection is general infrastructure (Sema). Clinical signal detection is domain-specific business logic (healthcare). They live in different layers because they solve different problems at different levels of abstraction.

## Components

| Component | Source | Role |
|-----------|--------|------|
| **Sema** | [withsema.com](https://withsema.com) | PII detection via Presidio, webhook delivery |
| **agent-registry-router** | [GitHub](https://github.com/agibson22/agent-registry-router) | Intent classification, PII-aware agent allowlist |
| **Interceptor** | This demo | Rule-based clinical signal detection (symptoms, medications, risk factors) |

## Demo Queries

**Query 1 — Safe** (no PII, no clinical signals):

> "How do I book an appointment?"

Routes to the general agent. Nothing flags. Baseline behavior.

**Query 2 — Full pipeline** (PII + clinical signals):

> "Schedule a follow-up for Jane Smith, DOB 04/12/1978. She mentioned during her last visit that she's been skipping her Lisinopril and has been having chest pain."

- Sema detects PII: `PERSON` (Jane Smith), `DATE_TIME` (04/12/1978)
- Classifier filters to PII-safe agents, routes to `receptionist`
- Interceptor flags: `chest_pain` (symptom), `Lisinopril` (medication), `skipping` (non-adherence)
- Decision support agent raises clinical alert

Same pipeline, completely different behavior.

## Setup

### Prerequisites

- Python 3.12+
- A Sema account with an inbox configured for PII enrichment
- [ngrok](https://ngrok.com) to expose the local webhook listener
- An OpenAI API key

### Install

```bash
make install
```

### Configure

```bash
cp .env.example .env
# Fill in your values
```

### Run

```bash
# Start ngrok in a separate terminal
ngrok http 5050

# Update your Sema inbox webhook URL to the ngrok HTTPS URL + /webhook

# Run the demo
make run        # interactive query selection
make safe       # query 1 (no PII, no clinical)
make full       # query 2 (PII + clinical signals)
```

## Files

| File | Purpose |
|------|---------|
| `cli.py` | Entry point — starts server, submits query, streams output |
| `pipeline.py` | Flask webhook listener, parallel dispatch, event queue |
| `agents.py` | Agent registry, PII-aware filtering, OpenAI classifier |
| `interceptor.py` | Rule-based clinical signal detection |
