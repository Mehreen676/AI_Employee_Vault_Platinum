"""
AI Employee Vault – Platinum Tier
Company Day Simulation  |  simulate_company_day.py

Generates ~50 realistic company tasks across:
  - Email tasks           (send_email, reply_email, email_processing)
  - Invoice / payment     (create_invoice, odoo)
  - Calendar events       (schedule_meeting, set_reminder)
  - CRM updates           (crm_update)
  - Social media posts    (social_post)
  - Document generation   (generate_report, summarize_document)

Pushes all tasks directly into vault/Needs_Action/
Generates Evidence/SIMULATION_REPORT.md

Usage:
    python simulate_company_day.py              # 50 tasks
    python simulate_company_day.py --n 20       # custom count
    python simulate_company_day.py --dry-run    # preview without writing
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Path helpers ───────────────────────────────────────────────────────────────

REPO_ROOT    = Path(__file__).resolve().parent
VAULT_DIR    = Path(os.getenv("VAULT_DIR",     str(REPO_ROOT / "vault")))
EVIDENCE_DIR = Path(os.getenv("EVIDENCE_OUT_DIR", str(REPO_ROOT / "Evidence")))


# ── Task catalogue ─────────────────────────────────────────────────────────────

TASK_TEMPLATES: list[dict[str, Any]] = [
    # Email tasks
    {"task_type": "send_email",      "zone": "email",    "content": "Send Q2 performance summary to all department heads"},
    {"task_type": "send_email",      "zone": "email",    "content": "Draft a follow-up email to client Acme Corp re: pending proposal"},
    {"task_type": "send_email",      "zone": "email",    "content": "Send onboarding welcome email to new hire Sarah Johnson"},
    {"task_type": "send_email",      "zone": "email",    "content": "Reply to vendor GlobalTech about delivery timeline for order #4521"},
    {"task_type": "send_email",      "zone": "email",    "content": "Send meeting recap to the engineering team after sprint review"},
    {"task_type": "email_processing","zone": "email",    "content": "Process support ticket from customer ID 8823 regarding billing issue"},
    {"task_type": "email_processing","zone": "email",    "content": "Route urgent escalation from enterprise client to account manager"},
    {"task_type": "send_email",      "zone": "email",    "content": "Send weekly newsletter to 1,200 subscriber list"},
    {"task_type": "send_email",      "zone": "email",    "content": "Notify all contractors about updated NDA requirements"},
    {"task_type": "send_email",      "zone": "email",    "content": "Send conference attendance confirmation to event organizers"},

    # Invoice / finance
    {"task_type": "create_invoice",  "zone": "finance",  "content": "Create draft invoice #INV-2026-042 for Acme Corp — 60 hours consulting at $200/hr"},
    {"task_type": "create_invoice",  "zone": "finance",  "content": "Generate monthly retainer invoice for client GlobalMedia — $8,500"},
    {"task_type": "odoo",            "zone": "finance",  "content": "Create partner: TechVentures LLC, Create draft invoice: 5,000 AED"},
    {"task_type": "create_invoice",  "zone": "finance",  "content": "Issue credit note for returned goods — order #ORD-8811"},
    {"task_type": "odoo",            "zone": "finance",  "content": "Create partner: SkyBridge Partners, Create draft invoice: 12,000 AED"},
    {"task_type": "create_invoice",  "zone": "finance",  "content": "Prepare pro-forma invoice for government tender #GOV-2026-15"},

    # Calendar / scheduling
    {"task_type": "schedule_meeting","zone": "calendar", "content": "Schedule Q2 board review — 2 hours, invite all C-level executives, conference room A"},
    {"task_type": "schedule_meeting","zone": "calendar", "content": "Book weekly 1:1 series with new team member (Mondays 10am, 8 weeks)"},
    {"task_type": "set_reminder",    "zone": "calendar", "content": "Set reminder: contract renewal for Acme Corp due in 30 days"},
    {"task_type": "schedule_meeting","zone": "calendar", "content": "Schedule product demo with investor group — 45 min video call"},
    {"task_type": "set_reminder",    "zone": "calendar", "content": "Remind CEO: quarterly report submission deadline next Friday"},
    {"task_type": "schedule_meeting","zone": "calendar", "content": "Book travel and hotel for Dubai AI Summit (March 15-17)"},
    {"task_type": "schedule_meeting","zone": "calendar", "content": "Schedule cross-team retrospective after system migration"},
    {"task_type": "set_reminder",    "zone": "calendar", "content": "Set payroll processing reminder for 25th of each month"},

    # CRM updates
    {"task_type": "crm_update",      "zone": "docs",     "content": "Update CRM: Acme Corp deal stage → Proposal Sent, value $120,000"},
    {"task_type": "crm_update",      "zone": "docs",     "content": "Log call notes: GlobalTech call — discussed SLA terms, follow-up in 2 weeks"},
    {"task_type": "crm_update",      "zone": "docs",     "content": "Mark lead ClientX as 'Qualified' after discovery call"},
    {"task_type": "crm_update",      "zone": "docs",     "content": "Update contact info for 3 accounts after business card import"},
    {"task_type": "crm_update",      "zone": "docs",     "content": "Close deal ID 2204 — won, revenue $45,000 AED"},
    {"task_type": "crm_update",      "zone": "docs",     "content": "Archive stale leads older than 90 days without activity"},

    # Social media
    {"task_type": "social_post",     "zone": "social",   "content": "Publish LinkedIn article: 'How AI is transforming enterprise task management in 2026'"},
    {"task_type": "social_post",     "zone": "social",   "content": "Post product launch announcement to all social channels — new AI Vault feature"},
    {"task_type": "social_post",     "zone": "social",   "content": "Share Q1 company milestone: 1,000 tasks automated this quarter"},
    {"task_type": "social_post",     "zone": "social",   "content": "Tweet thread: 5 reasons enterprises choose AI-driven task automation"},
    {"task_type": "social_post",     "zone": "social",   "content": "Publish Instagram story: behind-the-scenes of the AI team"},
    {"task_type": "social_post",     "zone": "social",   "content": "Post job opening: Senior ML Engineer — share across LinkedIn and Twitter"},

    # Document generation
    {"task_type": "generate_report", "zone": "docs",     "content": "Generate monthly operations report for March 2026 including KPIs and SLA metrics"},
    {"task_type": "summarize_document","zone": "docs",   "content": "Summarize 40-page vendor contract for legal review — highlight key obligations"},
    {"task_type": "generate_report", "zone": "docs",     "content": "Produce weekly sales pipeline report with funnel analysis"},
    {"task_type": "summarize_document","zone": "docs",   "content": "Summarize customer feedback survey results (n=340) into executive brief"},
    {"task_type": "generate_report", "zone": "docs",     "content": "Generate IT infrastructure health report including uptime and incident stats"},
    {"task_type": "summarize_document","zone": "docs",   "content": "Condense board meeting minutes into 1-page action item summary"},
    {"task_type": "generate_report", "zone": "docs",     "content": "Create compliance audit trail report for ISO 27001 review"},
    {"task_type": "summarize_document","zone": "docs",   "content": "Summarize employee satisfaction survey — flag critical issues"},

    # Mixed / edge cases
    {"task_type": "send_email",      "zone": "email",    "content": "Send automated status update to 50 project stakeholders"},
    {"task_type": "crm_update",      "zone": "docs",     "content": "Bulk update 200 contact records after data migration"},
    {"task_type": "schedule_meeting","zone": "calendar", "content": "Coordinate logistics for annual company offsite — 80 people, 3 days"},
    {"task_type": "social_post",     "zone": "social",   "content": "Respond to 15 customer comments on product announcement post"},
]


# ── Task writer ────────────────────────────────────────────────────────────────

def _write_task(template: dict[str, Any], dry_run: bool) -> tuple[str, str]:
    """Write one task to vault/Needs_Action/ and return (filename, zone)."""
    task_id = str(uuid.uuid4())
    task = {
        "id":         task_id,
        "task_type":  template["task_type"],
        "zone":       template["zone"],
        "content":    template["content"],
        "source":     "company_simulation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status":     "pending",
    }

    dest_dir = VAULT_DIR / "Needs_Action"
    dest_dir.mkdir(parents=True, exist_ok=True)

    ts       = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"sim_{ts}_{task_id[:8]}.json"
    dest     = dest_dir / filename
    tmp      = dest_dir / f".tmp_{filename}"

    if not dry_run:
        tmp.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.rename(dest)

    return filename, template["zone"]


# ── Report writer ──────────────────────────────────────────────────────────────

def _write_report(tasks_written: list[tuple[str, str, str]], dry_run: bool) -> None:
    from collections import Counter

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    report_path = EVIDENCE_DIR / "SIMULATION_REPORT.md"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    zone_counts = Counter(zone for _, zone, _ in tasks_written)
    type_counts = Counter(tt for _, _, tt in tasks_written)

    zone_rows = "\n".join(f"| {z} | {n} |" for z, n in sorted(zone_counts.items()))
    type_rows = "\n".join(f"| `{tt}` | {n} |" for tt, n in type_counts.most_common())

    task_list = "\n".join(
        f"| `{fname}` | {zone} | {tt} |"
        for fname, zone, tt in tasks_written[:20]
    )
    suffix = f"\n*... and {len(tasks_written) - 20} more tasks*" if len(tasks_written) > 20 else ""

    mode_note = "**DRY RUN** — no files written to vault" if dry_run else f"Tasks written to `vault/Needs_Action/`"

    report = f"""# Company Simulation Report

**Generated:** {ts}
**Mode:** {mode_note}
**Total tasks generated:** **{len(tasks_written)}**

---

## Task Breakdown by Zone

| Zone | Count |
|---|---|
{zone_rows}

## Task Breakdown by Type

| Task Type | Count |
|---|---|
{type_rows}

---

## First 20 Task Files

| Filename | Zone | Task Type |
|---|---|---|
{task_list}{suffix}

---

## Simulation Notes

- All tasks injected into `vault/Needs_Action/` for Cloud Agent pickup
- High-risk tasks (finance/odoo) will be routed through HITL gate
- Social posts subject to rate limit: ≤ 20/hr
- Email tasks subject to rate limit: ≤ 10/hr
- Payment/Odoo tasks carry `no_auto_retry` flag when they fail

---

*Generated by `simulate_company_day.py` — AI Employee Vault Platinum Tier*
"""

    report_path.write_text(report, encoding="utf-8")
    print(f"\n[simulation] Report written to {report_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def run_simulation(n: int = 50, dry_run: bool = False) -> None:
    print(f"[simulation] Generating {n} tasks {'(DRY RUN)' if dry_run else '→ vault/Needs_Action/'}")
    print()

    pool  = TASK_TEMPLATES.copy()
    random.shuffle(pool)

    # Cycle through templates if n > len(pool)
    selected: list[dict] = []
    while len(selected) < n:
        batch = pool.copy()
        random.shuffle(batch)
        selected.extend(batch)
    selected = selected[:n]

    tasks_written: list[tuple[str, str, str]] = []
    zone_counts: dict[str, int] = {}

    for i, template in enumerate(selected, 1):
        filename, zone = _write_task(template, dry_run)
        tasks_written.append((filename, zone, template["task_type"]))
        zone_counts[zone] = zone_counts.get(zone, 0) + 1
        print(f"  [{i:02d}/{n}] {template['task_type']:<25} zone={zone:<10}  {template['content'][:55]}")
        time.sleep(0.01)  # small delay to ensure unique timestamps

    print()
    print("[simulation] Zone summary:")
    for zone, count in sorted(zone_counts.items()):
        print(f"  {zone:<15} {count} tasks")

    _write_report(tasks_written, dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Vault Company Day Simulation")
    parser.add_argument("--n",       type=int, default=50, help="Number of tasks to generate (default: 50)")
    parser.add_argument("--dry-run", action="store_true",  help="Preview without writing to vault")
    args = parser.parse_args()

    run_simulation(n=args.n, dry_run=args.dry_run)
