"""Swiss Cheese Healthcare Demo — CLI entry point.

Starts a local webhook listener, submits a healthcare query to Sema,
and streams pipeline events to the terminal as they happen.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import queue
import sys
import threading
import time

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from sema_sdk import SemaClient

import pipeline

load_dotenv()

logging.getLogger("sema_sdk").setLevel(logging.ERROR)

console = Console()

QUERIES = {
    1: "How do I book an appointment?",
    2: (
        "Schedule a follow-up for Jane Smith, DOB 04/12/1978. "
        "She mentioned during her last visit that she's been skipping "
        "her Lisinopril and has been having chest pain."
    ),
}


def select_query(args: argparse.Namespace) -> str:
    if args.query:
        q = QUERIES.get(args.query)
        if not q:
            console.print(f"[red]Unknown query number: {args.query}[/red]")
            sys.exit(1)
        return q

    console.print()
    console.print("[bold]Select a query:[/bold]")
    for num, text in QUERIES.items():
        preview = text[:80] + ("..." if len(text) > 80 else "")
        console.print(f"  [cyan]{num}[/cyan]  {preview}")
    console.print()

    choice = console.input("[bold]Enter query number: [/bold]").strip()
    try:
        return QUERIES[int(choice)]
    except (ValueError, KeyError):
        console.print("[red]Invalid selection.[/red]")
        sys.exit(1)


def start_server() -> None:
    """Start Flask in a daemon thread with all output suppressed."""
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    import flask.cli

    flask.cli.show_server_banner = lambda *_: None

    thread = threading.Thread(
        target=lambda: pipeline.app.run(port=5050, use_reloader=False),
        daemon=True,
    )
    thread.start()
    time.sleep(0.3)


def submit_to_sema(query: str) -> str:
    """Upload the query to a Sema inbox. Returns the item ID."""
    client = SemaClient(
        api_key=os.environ["SEMA_API_KEY"],
        base_url=os.environ.get("SEMA_BASE_URL", "https://dev-api.withsema.com"),
    )
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    body = f"[{timestamp}] {query}"
    result = client.upload_item(
        inbox_id=os.environ["SEMA_INBOX_ID"],
        file=io.BytesIO(body.encode()),
        sender_address="demo@swiss-cheese.local",
        subject=query[:100],
        content_type="text/plain",
    )
    if result.is_duplicate:
        console.print("  [yellow]![/yellow] Duplicate item — Sema may skip reprocessing")
    return result.id


def render_event(evt: pipeline.PipelineEvent) -> None:
    """Render a single pipeline event to the console."""
    elapsed = f"[dim]{evt.elapsed:.1f}s[/dim]"
    d = evt.data

    if evt.stage == "webhook_received":
        console.print(Rule(" Sema ", style="dim"))
        console.print(f"  [green]>[/green] Webhook received from Sema          {elapsed}")

    elif evt.stage == "pii_result":
        if d.get("pii_detected"):
            types = ", ".join(d.get("by_type", {}).keys())
            console.print(
                f"  [green]>[/green] PII detected: [bold yellow]{types}[/bold yellow]          {elapsed}"
            )
            console.print(
                f"    Risk level: [bold]{d.get('risk_level', 'unknown')}[/bold]  |  "
                f"Entities: {d.get('entity_count', 0)}"
            )
        else:
            console.print(f"  [green]>[/green] PII: [dim]none detected[/dim]                    {elapsed}")

    elif evt.stage == "classifier_started":
        console.print(Rule(" Routing ", style="dim"))
        console.print(f"  [blue]>[/blue] Classifier dispatched...              {elapsed}")

    elif evt.stage == "classifier_result":
        agent = d.get("agent", "?")
        confidence = d.get("confidence", 0)
        pii_flag = "[yellow]PII-filtered[/yellow]" if d.get("pii_filtered") else "[dim]full registry[/dim]"
        console.print(
            f"  [green]>[/green] Classifier -> [bold cyan]{agent}[/bold cyan] "
            f"(confidence: {confidence:.2f})   {elapsed}"
        )
        console.print(f"    {pii_flag}  |  {d.get('reasoning', '')}")

    elif evt.stage == "interceptor_started":
        console.print(f"  [blue]>[/blue] Interceptor dispatched...             {elapsed}")

    elif evt.stage == "interceptor_result":
        signals = d.get("signals", [])
        if signals:
            terms = " . ".join(s["term"] for s in signals)
            console.print(
                f"  [green]>[/green] Interceptor -> [bold red]{len(signals)} clinical signal(s)[/bold red]   {elapsed}"
            )
            console.print(f"    {terms}")
        else:
            console.print(
                f"  [green]>[/green] Interceptor: [dim]no clinical signals[/dim]     {elapsed}"
            )

    elif evt.stage == "aggregated":
        render_summary(d, evt.elapsed)

    elif evt.stage == "error":
        console.print(f"  [red]![/red] Error: {d.get('message', 'unknown')}   {elapsed}")


def render_summary(data: dict, total_elapsed: float) -> None:
    """Render the final aggregated summary panel."""
    console.print()

    classifier = data.get("classifier", {})
    interceptor = data.get("interceptor", {})

    lines = Text()

    lines.append("Classifier", style="bold")
    lines.append(f"  ->  {classifier.get('agent', '?')}", style="cyan")
    lines.append(f"  (confidence: {classifier.get('confidence', 0):.2f})\n")
    if classifier.get("pii_filtered"):
        lines.append("  Registry: PII-filtered (general excluded)\n", style="yellow")
    else:
        lines.append("  Registry: full (all agents eligible)\n", style="dim")
    if classifier.get("response"):
        lines.append(f"  {classifier['response']}\n\n", style="dim")

    if interceptor.get("clinical_alert"):
        lines.append("Interceptor", style="bold")
        lines.append("  ->  decision_support\n", style="red")
        signals = interceptor.get("signals", [])
        for s in signals:
            lines.append(f"  [{s['type']}] ", style="yellow")
            lines.append(f"{s['term']}\n")
        if interceptor.get("response"):
            lines.append(f"\n  {interceptor['response']}\n", style="dim")
    else:
        lines.append("Interceptor", style="bold")
        lines.append("  ->  no clinical signals\n", style="dim")

    title = f"Results  ({total_elapsed:.1f}s total)"
    console.print(Panel(lines, title=title, border_style="green", padding=(1, 2)))


def run_query(query: str) -> None:
    """Run a single query through the pipeline with streaming output."""
    console.print()
    console.print(Rule("swiss-cheese \u2014 layered safety for healthcare AI", style="blue"))
    console.print()
    console.print(Panel(query, title="Inbound Inquiry", border_style="blue", padding=(1, 2)))
    console.print()

    t0 = time.time()
    try:
        item_id = submit_to_sema(query)
    except Exception as e:
        console.print(f"  [red]Failed to submit to Sema: {e}[/red]")
        sys.exit(1)

    console.print(f"  [green]>[/green] Submitted to Swiss Cheese Healthcare Sema Inbox   [dim]{time.time() - t0:.1f}s[/dim]")

    with console.status("[dim]Waiting for Sema to process...[/dim]", spinner="dots"):
        try:
            first_evt = pipeline.event_queue.get(timeout=60)
        except queue.Empty:
            console.print("  [red]Timed out waiting for webhook (60s)[/red]")
            sys.exit(1)

    render_event(first_evt)
    if first_evt.stage == "aggregated":
        return

    while True:
        try:
            evt = pipeline.event_queue.get(timeout=60)
        except queue.Empty:
            console.print("  [red]Timed out waiting for pipeline (60s)[/red]")
            sys.exit(1)

        render_event(evt)

        if evt.stage == "aggregated":
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Swiss Cheese Healthcare Demo")
    parser.add_argument("--query", type=int, choices=[1, 2], help="Query number (1=safe, 2=full)")
    parser.add_argument("--demo", action="store_true", help="Run both queries back-to-back")
    args = parser.parse_args()

    required_vars = ["SEMA_WEBHOOK_SECRET", "SEMA_API_KEY", "SEMA_INBOX_ID", "OPENAI_API_KEY"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        console.print(f"[red]Missing env vars: {', '.join(missing)}[/red]")
        console.print("Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    pipeline.init(
        webhook_secret=os.environ["SEMA_WEBHOOK_SECRET"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )
    start_server()

    if args.demo:
        run_query(QUERIES[1])
        console.print()
        console.print(Rule(" next query ", style="bold blue"))
        run_query(QUERIES[2])
    else:
        query = select_query(args)
        run_query(query)


if __name__ == "__main__":
    main()
