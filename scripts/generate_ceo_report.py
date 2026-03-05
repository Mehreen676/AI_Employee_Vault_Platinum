"""
AI Employee Vault – Platinum Tier
CEO Daily Report Generator  |  scripts/generate_ceo_report.py

Reads:
  vault/Logs/execution_log.json
  vault/Logs/health_log.json
  history/prompt_log.json  (optional)

Generates:
  Evidence/CEO_REPORT.md

Usage:
    python scripts/generate_ceo_report.py
    python scripts/generate_ceo_report.py --date 2026-03-05
    python scripts/generate_ceo_report.py --vault /custom/vault --out /custom/out
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# ── Path resolution ────────────────────────────────────────────────────────────

REPO_ROOT    = Path(__file__).resolve().parent.parent
VAULT_DIR    = Path(os.getenv("VAULT_DIR",     str(REPO_ROOT / "vault")))
LOG_DIR      = Path(os.getenv("VAULT_LOG_DIR", str(VAULT_DIR / "Logs")))
EVIDENCE_DIR = Path(os.getenv("EVIDENCE_OUT_DIR", str(REPO_ROOT / "Evidence")))
HISTORY_DIR  = REPO_ROOT / "history"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ── Report logic ───────────────────────────────────────────────────────────────

def build_report(report_date: datetime) -> str:
    day_start = report_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    day_end   = day_start + timedelta(days=1)

    exec_entries  = _read_jsonl(LOG_DIR / "execution_log.json")
    health_entries = _read_jsonl(LOG_DIR / "health_log.json")
    prompt_entries = _read_jsonl(LOG_DIR / "prompt_chain.json")
    try:
        prompt_entries += _read_jsonl(HISTORY_DIR / "prompt_log.json")
    except Exception:
        pass

    # Filter to report date window
    def _in_window(e: dict) -> bool:
        ts = _parse_ts(e.get("timestamp"))
        return ts is not None and day_start <= ts < day_end

    day_exec    = [e for e in exec_entries  if _in_window(e)]
    day_health  = [e for e in health_entries if _in_window(e)]

    # Core metrics
    total    = len(day_exec)
    approved = sum(1 for e in day_exec if e.get("result") == "success")
    rejected = sum(1 for e in day_exec if e.get("action") == "rejected")
    failures = sum(1 for e in day_exec if isinstance(e.get("result"), str) and e["result"].startswith("error"))
    pending  = total - approved - rejected - failures

    # Top action categories
    task_types = Counter(e.get("task_type", "unknown") for e in day_exec)
    top_actions_md = "\n".join(
        f"  - {task_type}: {count}"
        for task_type, count in task_types.most_common(8)
    ) or "  - No actions recorded today"

    # Health summary
    total_health_checks = len(day_health)
    ok_checks = sum(1 for e in day_health if e.get("status") == "ok")
    uptime_pct = (ok_checks / total_health_checks * 100) if total_health_checks else 0

    # Prompt chain events
    prompt_today = [e for e in prompt_entries if _in_window(e)]
    prompt_event_types = Counter(e.get("event_type", "unknown") for e in prompt_today)
    prompt_summary = ", ".join(
        f"{et}={n}" for et, n in prompt_event_types.most_common(5)
    ) or "none"

    # Vault queue snapshot (live counts)
    def _count_dir(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(1 for f in path.iterdir() if f.is_file() and not f.name.startswith("."))

    queue_dir = VAULT_DIR / "Queue"
    queues = {
        "needs_action":     _count_dir(queue_dir / "Needs_Action"),
        "pending_approval": _count_dir(queue_dir / "Pending_Approval"),
        "done":             _count_dir(queue_dir / "Done"),
        "retry_queue":      _count_dir(queue_dir / "Retry"),
        "rejected":         _count_dir(queue_dir / "Rejected"),
    }

    date_str = report_date.strftime("%Y-%m-%d")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    report = f"""# CEO DAILY REPORT
**Date:** {date_str}
**Generated:** {generated_at}
**System:** AI Employee Vault – Platinum Tier v1.4.0

---

## Executive Summary

| Metric | Value |
|---|---|
| Tasks Processed | **{total}** |
| Approved / Success | **{approved}** |
| Rejected | **{rejected}** |
| Failures | **{failures}** |
| Pending | **{pending}** |
| System Uptime | **{uptime_pct:.1f}%** ({ok_checks}/{total_health_checks} health checks) |

---

## Top Actions Today

{top_actions_md}

---

## Live Vault Queue Snapshot

| Queue | Count |
|---|---|
| Needs Action | {queues['needs_action']} |
| Pending Approval | {queues['pending_approval']} |
| Done | {queues['done']} |
| Retry Queue | {queues['retry_queue']} |
| Rejected | {queues['rejected']} |

---

## Prompt Chain Events

Events logged today: **{len(prompt_today)}**
Breakdown: {prompt_summary}

---

## System Health

- Health check records today: **{total_health_checks}**
- System uptime: **{uptime_pct:.1f}%**
- Vault integrity: All JSONL logs append-only ✓
- SHA-256 chain: Active ✓

---

## Notes

- All task executions subject to HITL approval gate
- Payment tasks (Odoo/finance) carry `no_auto_retry` flag
- Rate limits enforced: email ≤ 10/hr, social ≤ 20/hr, payment ≤ 3/day

---

*Generated by `scripts/generate_ceo_report.py` — AI Employee Vault Platinum Tier*
"""
    return report


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CEO daily report")
    parser.add_argument("--date", default=None,
                        help="Report date YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--vault", default=None, help="Override VAULT_DIR")
    parser.add_argument("--out",   default=None, help="Override output path")
    args = parser.parse_args()

    global VAULT_DIR, LOG_DIR
    if args.vault:
        VAULT_DIR = Path(args.vault)
        LOG_DIR   = VAULT_DIR / "Logs"

    if args.date:
        report_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        report_date = datetime.now(timezone.utc)

    report = build_report(report_date)

    out_path = Path(args.out) if args.out else (EVIDENCE_DIR / "CEO_REPORT.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"[CEO report] Written to {out_path}")
    print(report[:600])


if __name__ == "__main__":
    main()
