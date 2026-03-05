"""
AI Employee Vault – Platinum Tier
AI Decision Logger  |  integrations/ai_decision_logger.py

For every task execution, records:
  - Task ID and type
  - Reasoning / intent summary
  - Selected MCP tool
  - Risk level (low / medium / high / critical)
  - Final action taken
  - Outcome

Output: Evidence/AI_DECISION_LOG.md  (append-only markdown)
        vault/Logs/ai_decisions.json  (JSONL for programmatic access)

Usage (as a library):
    from integrations.ai_decision_logger import log_decision

    log_decision(
        task_id="abc-123",
        task_type="send_email",
        content="Send invoice to Acme Corp",
        tool_selected="email_mcp",
        reasoning="Task contains 'send' + 'invoice' → email tool selected",
        risk_level="low",
        action_taken="draft email prepared",
        outcome="success",
    )
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

_lock = threading.Lock()

RiskLevel = Literal["low", "medium", "high", "critical"]


# ── Path helpers ───────────────────────────────────────────────────────────────

def _vault_dir() -> Path:
    return Path(os.getenv("VAULT_DIR", str(Path(__file__).resolve().parent.parent / "vault")))

def _evidence_dir() -> Path:
    return Path(os.getenv("EVIDENCE_OUT_DIR", str(Path(__file__).resolve().parent.parent / "Evidence")))


# ── Risk classifier ────────────────────────────────────────────────────────────

_RISK_MAP: dict[str, RiskLevel] = {
    "odoo":            "critical",
    "payment":         "critical",
    "create_invoice":  "high",
    "social_post":     "high",
    "send_email":      "medium",
    "schedule_meeting":"low",
    "crm_update":      "medium",
    "generate_report": "low",
    "summarize":       "low",
    "email_processing":"medium",
    "evidence_generation": "low",
    "hitl_decision":   "medium",
}

def infer_risk(task_type: str) -> RiskLevel:
    return _risk_map_lookup(task_type.lower())

def _risk_map_lookup(tt: str) -> RiskLevel:
    for key, level in _RISK_MAP.items():
        if key in tt:
            return level
    return "low"


# ── Tool selector ──────────────────────────────────────────────────────────────

_TOOL_MAP: dict[str, str] = {
    "email":    "email_mcp",
    "invoice":  "odoo_client",
    "payment":  "odoo_client",
    "odoo":     "odoo_client",
    "calendar": "calendar_mcp",
    "schedule": "calendar_mcp",
    "social":   "social_mcp",
    "post":     "social_mcp",
    "file":     "file_mcp",
    "report":   "file_mcp",
    "crm":      "file_mcp",
}

def infer_tool(task_type: str, content: str) -> str:
    combined = (task_type + " " + content).lower()
    for keyword, tool in _TOOL_MAP.items():
        if keyword in combined:
            return tool
    return "general_executor"


# ── Core logging function ──────────────────────────────────────────────────────

def log_decision(
    task_id: str,
    task_type: str,
    content: str,
    tool_selected: str | None = None,
    reasoning: str | None = None,
    risk_level: RiskLevel | None = None,
    action_taken: str = "task_executed",
    outcome: str = "success",
    metadata: dict | None = None,
) -> None:
    """
    Append one AI decision record to Evidence/AI_DECISION_LOG.md and
    vault/Logs/ai_decisions.json.

    Can be called from cloud_agent, local_executor, or any integration.
    Thread-safe; uses a module-level lock.
    """
    ts = datetime.now(timezone.utc).isoformat()

    # Auto-infer missing fields
    if tool_selected is None:
        tool_selected = infer_tool(task_type, content)
    if risk_level is None:
        risk_level = infer_risk(task_type)
    if reasoning is None:
        reasoning = f"Task type '{task_type}' matched tool '{tool_selected}' (auto-inferred)"

    record = {
        "timestamp":    ts,
        "task_id":      task_id,
        "task_type":    task_type,
        "content":      content[:300],
        "tool":         tool_selected,
        "reasoning":    reasoning,
        "risk_level":   risk_level,
        "action_taken": action_taken,
        "outcome":      outcome,
    }
    if metadata:
        record["metadata"] = metadata

    with _lock:
        _write_jsonl(record)
        _write_markdown(record)


def _write_jsonl(record: dict) -> None:
    log_path = _vault_dir() / "Logs" / "ai_decisions.json"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("[ai_decision] JSONL write failed: %s", exc)


_RISK_EMOJI: dict[str, str] = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
}

def _write_markdown(record: dict) -> None:
    ev_dir = _evidence_dir()
    ev_dir.mkdir(parents=True, exist_ok=True)
    log_path = ev_dir / "AI_DECISION_LOG.md"

    ts_fmt = record["timestamp"].replace("T", " ").replace("+00:00", " UTC")[:23] + " UTC"
    risk   = record["risk_level"]
    emoji  = _RISK_EMOJI.get(risk, "⚪")

    entry = (
        f"\n### {ts_fmt} — `{record['task_type']}`\n"
        f"| Field | Value |\n|---|---|\n"
        f"| Task ID | `{record['task_id']}` |\n"
        f"| Task Type | `{record['task_type']}` |\n"
        f"| Tool Selected | `{record['tool']}` |\n"
        f"| Risk Level | {emoji} **{risk.upper()}** |\n"
        f"| Action Taken | `{record['action_taken']}` |\n"
        f"| Outcome | `{record['outcome']}` |\n"
        f"\n**Reasoning:** {record['reasoning']}\n"
        f"\n**Content:** {record['content'][:200]}\n"
    )

    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(entry)
    except OSError as exc:
        log.warning("[ai_decision] markdown write failed: %s", exc)


# ── Ensure header exists ───────────────────────────────────────────────────────

def _ensure_header() -> None:
    ev_dir = _evidence_dir()
    ev_dir.mkdir(parents=True, exist_ok=True)
    log_path = ev_dir / "AI_DECISION_LOG.md"
    if not log_path.exists() or log_path.stat().st_size == 0:
        log_path.write_text(
            "# AI Decision Log\n\n"
            "Append-only record of every AI decision made by Cloud Agent and Local Executor.\n\n"
            "| Risk | Meaning |\n|---|---|\n"
            "| 🔴 CRITICAL | Payment / Odoo — requires human review |\n"
            "| 🟠 HIGH | Social posts, invoice creation |\n"
            "| 🟡 MEDIUM | Email, CRM updates |\n"
            "| 🟢 LOW | Reports, calendar, file ops |\n\n"
            "---\n",
            encoding="utf-8",
        )

_ensure_header()
