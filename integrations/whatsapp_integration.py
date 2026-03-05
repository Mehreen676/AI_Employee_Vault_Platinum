"""
AI Employee Vault – Platinum Tier
WhatsApp Integration (Twilio)  |  integrations/whatsapp_integration.py

Handles Twilio WhatsApp webhook payloads → vault tasks.

Used by the FastAPI backend endpoint: POST /whatsapp/webhook
Twilio sends form-encoded POST data (not JSON).

Each WhatsApp message is converted to a task manifest and written to:
    vault/Needs_Action/

Activity logged to: Evidence/WHATSAPP_INTEGRATION_LOG.md
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Path helpers ───────────────────────────────────────────────────────────────

def _vault_dir() -> Path:
    return Path(os.getenv("VAULT_DIR", str(Path(__file__).resolve().parent.parent / "vault")))

def _evidence_dir() -> Path:
    return Path(os.getenv("EVIDENCE_OUT_DIR", str(Path(__file__).resolve().parent.parent / "Evidence")))


# ── Twilio form payload parser ─────────────────────────────────────────────────

def parse_twilio_payload(form_data: dict[str, str]) -> dict[str, Any] | None:
    """
    Parse a Twilio WhatsApp webhook form payload.

    Twilio fields used:
      Body      — message text
      From      — sender WhatsApp number (e.g. whatsapp:+97150xxxxxxx)
      To        — receiving number
      MessageSid — Twilio message SID
    """
    body = form_data.get("Body", "").strip()
    if not body:
        return None

    sender     = form_data.get("From", "unknown")
    to         = form_data.get("To", "unknown")
    message_sid = form_data.get("MessageSid", str(uuid.uuid4()))

    return {
        "text":        body,
        "from":        sender,
        "to":          to,
        "message_sid": message_sid,
    }


# ── Message → task ─────────────────────────────────────────────────────────────

def whatsapp_message_to_task(message: dict[str, Any]) -> dict[str, Any]:
    text = message["text"]

    task_type = "whatsapp_message"
    zone      = "docs"
    if re.search(r"\b(invoice|payment|bill)\b", text, re.I):
        task_type, zone = "create_invoice", "finance"
    elif re.search(r"\b(email|send|message)\b", text, re.I):
        task_type, zone = "send_email", "email"
    elif re.search(r"\b(schedule|meeting|appointment)\b", text, re.I):
        task_type, zone = "schedule_meeting", "calendar"
    elif re.search(r"\b(post|publish|social|share)\b", text, re.I):
        task_type, zone = "social_post", "social"
    elif re.search(r"\b(update|crm|contact|client)\b", text, re.I):
        task_type, zone = "crm_update", "docs"

    return {
        "id":           str(uuid.uuid4()),
        "task_type":    task_type,
        "zone":         zone,
        "source":       "whatsapp_webhook",
        "from_number":  message["from"],
        "message_sid":  message["message_sid"],
        "content":      text[:1000],
        "created_at":   datetime.now(timezone.utc).isoformat(),
        "status":       "pending",
    }


# ── Vault writer ───────────────────────────────────────────────────────────────

def write_vault_task(task: dict[str, Any]) -> Path:
    dest_dir = _vault_dir() / "Needs_Action"
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"wa_{ts}_{task['id'][:8]}.json"
    dest     = dest_dir / filename
    tmp      = dest_dir / f".tmp_{filename}"
    tmp.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(dest)
    return dest


# ── Evidence log ───────────────────────────────────────────────────────────────

def log_evidence(message: dict, task: dict, dest: Path) -> None:
    ev_dir = _evidence_dir()
    ev_dir.mkdir(parents=True, exist_ok=True)
    log_path = ev_dir / "WHATSAPP_INTEGRATION_LOG.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(
            f"\n### {ts} — WhatsApp Message\n"
            f"- **From:** `{message.get('from', 'unknown')}`\n"
            f"- **Message SID:** `{message.get('message_sid', '')}`\n"
            f"- **Text:** {message.get('text', '')[:200]}\n"
            f"- **Task ID:** `{task['id']}`\n"
            f"- **Task Type:** `{task['task_type']}`\n"
            f"- **Vault file:** `{dest.name}`\n"
        )


# ── TwiML helper ───────────────────────────────────────────────────────────────

def make_twiml_response(message: str) -> str:
    """Return a minimal TwiML response for Twilio."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'<Message>{message}</Message>'
        '</Response>'
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def handle_webhook(form_data: dict[str, str]) -> dict[str, Any]:
    """
    Process a Twilio WhatsApp webhook form payload.
    Returns a response dict suitable for the FastAPI endpoint.
    """
    message = parse_twilio_payload(form_data)
    if message is None:
        return {"ok": True, "action": "ignored", "reason": "empty message body"}

    task = whatsapp_message_to_task(message)
    dest = write_vault_task(task)
    log_evidence(message, task, dest)
    log.info("[whatsapp] task %s written → %s", task["id"], dest.name)

    return {
        "ok":         True,
        "task_id":    task["id"],
        "task_type":  task["task_type"],
        "vault_file": dest.name,
        "twiml":      make_twiml_response("✅ Task received and queued for processing."),
    }
