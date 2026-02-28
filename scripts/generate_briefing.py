"""
AI Employee Vault – Platinum Tier
CEO Briefing Automation

Module:   scripts/generate_briefing.py
Version:  1.0.0

Responsibility:
    Generates a daily CEO briefing report in Briefings/YYYY-MM-DD_Briefing.md.

    The briefing pulls from three authoritative data sources:
        1. Business_Goals.md — current OKRs and revenue targets
        2. vault/Done/ — all completed task manifests (today + all-time summary)
        3. vault/Logs/execution_log.json — per-task execution results
        4. vault/Logs/health_log.json — process health (uptime, restarts)
        5. vault/Retry_Queue/ — tasks pending human review
        6. vault/Deferred/email/ — deferred email polls

    Briefing sections:
        - Header: date, generated-at, system status
        - Business Goals snapshot
        - Execution Summary (today's throughput, all-time totals)
        - Revenue Estimate (Odoo tasks: invoice amounts parsed from content)
        - Bottlenecks & Failures (Retry_Queue + error results)
        - Process Health (last watchdog cycle)
        - Suggestions (derived from bottlenecks and goal gaps)

CLI Usage (from project root):
    python scripts/generate_briefing.py
    python scripts/generate_briefing.py --date 2026-02-28
    python scripts/generate_briefing.py --out Briefings/custom_report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_VAULT_ROOT   = _PROJECT_ROOT / "vault"
_DONE_DIR     = _VAULT_ROOT / "Done"
_LOGS_DIR     = _VAULT_ROOT / "Logs"
_RETRY_QUEUE  = _VAULT_ROOT / "Retry_Queue"
_DEFERRED_DIR = _VAULT_ROOT / "Deferred" / "email"
_EXEC_LOG     = _LOGS_DIR / "execution_log.json"
_HEALTH_LOG   = _LOGS_DIR / "health_log.json"
_GOALS_FILE   = _PROJECT_ROOT / "Business_Goals.md"
_BRIEFINGS    = _PROJECT_ROOT / "Briefings"

# Regex to extract AED invoice amount from odoo task content.
_AMOUNT_RE = re.compile(r"Create draft invoice:\s*([\d.]+)\s*AED", re.IGNORECASE)


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return all successfully parsed records."""
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def _read_done_manifests() -> list[dict]:
    """Read all completed task manifests from vault/Done/."""
    if not _DONE_DIR.exists():
        return []
    manifests = []
    for f in _DONE_DIR.glob("*.json"):
        try:
            manifests.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return manifests


def _read_retry_queue() -> list[dict]:
    """Read all records from vault/Retry_Queue/."""
    if not _RETRY_QUEUE.exists():
        return []
    records = []
    for f in _RETRY_QUEUE.glob("*.json"):
        try:
            records.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return records


def _last_health_record() -> dict | None:
    """Return the most recent health log record, or None."""
    records = _read_jsonl(_HEALTH_LOG)
    return records[-1] if records else None


def _estimate_revenue(exec_records: list[dict]) -> float:
    """
    Parse AED amounts from odoo task execution records.

    Each execution_log record for odoo tasks does not store the amount
    directly, so we cross-reference Done/ manifests.
    """
    total = 0.0
    for manifest in _read_done_manifests():
        if manifest.get("task_type") != "odoo":
            continue
        content = manifest.get("content", "")
        m = _AMOUNT_RE.search(content)
        if m:
            try:
                total += float(m.group(1))
            except ValueError:
                pass
    return total


def _today_prefix(date_str: str) -> str:
    """Return 'YYYY-MM-DD' prefix for filtering ISO timestamps."""
    return date_str[:10]


def generate_briefing(date_str: str, out_path: Path) -> None:
    """
    Generate a CEO briefing for *date_str* (YYYY-MM-DD) and write to *out_path*.

    Args:
        date_str: Date to report on. Defaults to today.
        out_path: Destination markdown file path.
    """
    now_iso   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day_label = date_str

    # --- Execution log records ---
    all_exec = _read_jsonl(_EXEC_LOG)
    today_exec = [r for r in all_exec if r.get("timestamp", "").startswith(day_label)]

    total_tasks   = len(all_exec)
    today_tasks   = len(today_exec)
    today_success = sum(1 for r in today_exec if not str(r.get("result", "")).startswith("error"))
    today_errors  = today_tasks - today_success

    by_type: dict[str, int] = {}
    for r in today_exec:
        tt = r.get("task_type", "unknown")
        by_type[tt] = by_type.get(tt, 0) + 1

    # --- Revenue ---
    total_revenue = _estimate_revenue(all_exec)

    # --- Retry queue ---
    retry_records = _read_retry_queue()
    payment_retry = [r for r in retry_records if r.get("no_auto_retry")]
    other_retry   = [r for r in retry_records if not r.get("no_auto_retry")]

    # --- Deferred emails ---
    deferred_count = 0
    if _DEFERRED_DIR.exists():
        deferred_count = len(list(_DEFERRED_DIR.glob("*.json")))

    # --- Health ---
    health = _last_health_record()

    # --- Business Goals ---
    goals_content = ""
    if _GOALS_FILE.exists():
        goals_content = _GOALS_FILE.read_text(encoding="utf-8").strip()

    # --- Suggestions ---
    suggestions: list[str] = []
    if today_errors > 0:
        suggestions.append(
            f"**{today_errors} task(s) failed today** — review `vault/Retry_Queue/` "
            "and resolve root cause before next cycle."
        )
    if payment_retry:
        suggestions.append(
            f"**{len(payment_retry)} payment task(s) in Retry_Queue** flagged "
            "`no_auto_retry=True` — require immediate human review and manual re-queue."
        )
    if deferred_count > 0:
        suggestions.append(
            f"**{deferred_count} deferred email poll(s)** in `vault/Deferred/email/` "
            "— Gmail API may be rate-limited or credentials may need renewal."
        )
    if health and health.get("cloud_agent", {}).get("restarts", 0) > 0:
        restarts = health["cloud_agent"]["restarts"]
        suggestions.append(
            f"**Cloud Agent restarted {restarts}× in last watchdog cycle** "
            "— investigate `vault/Logs/health_log.json` for crash root cause."
        )
    if not suggestions:
        suggestions.append("No critical issues detected. All systems operating within normal parameters.")

    # --- Compose briefing ---
    lines = [
        f"# CEO Daily Briefing — {day_label}",
        "",
        f"**Generated:** {now_iso}",
        f"**System:** AI Employee Vault – Platinum Tier v1.4.0",
        "",
        "---",
        "",
        "## Business Goals",
        "",
        goals_content if goals_content else "_`Business_Goals.md` not found — add business objectives to enable goal-tracking._",
        "",
        "---",
        "",
        "## Execution Summary",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Tasks completed today ({day_label}) | {today_tasks} |",
        f"| Successful today | {today_success} |",
        f"| Failed today | {today_errors} |",
        f"| All-time total completed | {total_tasks} |",
        "",
        "### Today's Tasks by Type",
        "",
    ]

    if by_type:
        lines += ["| Task Type | Count |", "|---|---|"]
        for tt, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
            lines.append(f"| `{tt}` | {cnt} |")
    else:
        lines.append("_No tasks completed today._")

    lines += [
        "",
        "---",
        "",
        "## Revenue Estimate",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Estimated AED invoiced (all-time, draft) | AED {total_revenue:,.2f} |",
        "",
        "> **Note:** All Odoo invoices are in `state='draft'`. No revenue is recognised until a human confirms the invoice in Odoo.",
        "",
        "---",
        "",
        "## Bottlenecks & Failures",
        "",
    ]

    if retry_records:
        lines += [
            f"**{len(retry_records)} task(s) in `vault/Retry_Queue/`:**",
            "",
            "| Task ID | Type | Error | No Auto-Retry |",
            "|---|---|---|---|",
        ]
        for r in retry_records[:10]:  # Cap at 10 rows for readability.
            tid = r.get("task_id", "?")[:8]
            tt  = r.get("task_type", "?")
            err = r.get("error", "?")[:60]
            nar = "YES — human required" if r.get("no_auto_retry") else "No"
            lines.append(f"| `{tid}...` | `{tt}` | {err} | {nar} |")
        if len(retry_records) > 10:
            lines.append(f"| _(+{len(retry_records)-10} more)_ | | | |")
    else:
        lines.append("_No tasks in Retry_Queue. All operations completed or pending._")

    lines += [
        "",
        f"**Deferred email polls:** {deferred_count}",
        "_(Deferred polls mean the Gmail API was unavailable during that cycle.)_",
        "",
        "---",
        "",
        "## Process Health",
        "",
    ]

    if health:
        hts = health.get("timestamp", "?")
        lines += [
            f"**Last watchdog cycle:** {hts}  (cycle #{health.get('cycle', '?')})",
            "",
            "| Process | Alive | PID | Restarts |",
            "|---|---|---|---|",
        ]
        for proc in ("cloud_agent", "gmail_watcher", "local_executor"):
            ps    = health.get(proc, {})
            alive = "UP" if ps.get("alive") else "DOWN"
            pid   = ps.get("pid") or "—"
            rst   = ps.get("restarts", 0)
            label = proc.replace("_", " ").title()
            lines.append(f"| {label} | {alive} | {pid} | {rst} |")
    else:
        lines.append("_`vault/Logs/health_log.json` not found — start the Watchdog to enable health tracking._")

    lines += [
        "",
        "---",
        "",
        "## Suggestions",
        "",
    ]
    for s in suggestions:
        lines.append(f"- {s}")

    lines += [
        "",
        "---",
        "",
        f"_AI Employee Vault – Platinum Tier | CEO Briefing v1.0.0 | {now_iso}_",
        "",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[generate_briefing] Briefing written to: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate_briefing",
        description=(
            "AI Employee Vault – Platinum Tier: CEO Briefing Automation.\n"
            "Generates a daily executive summary from vault state, execution logs,\n"
            "health records, and Business_Goals.md."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Date to report on (default: today UTC).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="PATH",
        help="Output file path (default: Briefings/YYYY-MM-DD_Briefing.md).",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = _BRIEFINGS / f"{date_str}_Briefing.md"

    generate_briefing(date_str, out_path)


if __name__ == "__main__":
    main()
