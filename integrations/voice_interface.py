"""
AI Employee Vault – Platinum Tier
Voice Command Interface  |  integrations/voice_interface.py

Listens for voice commands → converts → vault tasks in vault/Needs_Action/voice/

Behaviour:
  - If SpeechRecognition + PyAudio are installed → live microphone input
  - Fallback → reads commands from stdin (useful in headless/CI environments)
  - Each recognized command is parsed into a task manifest
  - Written atomically to vault/Needs_Action/voice/
  - Activity logged to Evidence/VOICE_COMMAND_LOG.md

Usage:
    python -m integrations.voice_interface              # microphone mode (continuous)
    python -m integrations.voice_interface --once       # one command then exit
    python -m integrations.voice_interface --stdin      # read commands from stdin
    python -m integrations.voice_interface --text "send invoice to client Acme"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
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


# ── Intent parser ──────────────────────────────────────────────────────────────

_INTENT_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\b(send|draft|write|compose)\b.*\b(email|mail|message)\b", re.I), "email",    "send_email"),
    (re.compile(r"\b(invoice|bill|payment|charge)\b",                         re.I), "finance",  "create_invoice"),
    (re.compile(r"\b(schedule|book|meeting|calendar|appointment)\b",          re.I), "calendar", "schedule_meeting"),
    (re.compile(r"\b(post|tweet|publish|social|linkedin|instagram)\b",        re.I), "social",   "social_post"),
    (re.compile(r"\b(crm|contact|client|customer|partner)\b",                 re.I), "docs",     "crm_update"),
    (re.compile(r"\b(report|summary|briefing|update)\b",                      re.I), "docs",     "generate_report"),
    (re.compile(r"\b(remind|reminder|follow.?up)\b",                          re.I), "calendar", "set_reminder"),
]

def _parse_command(text: str) -> dict[str, Any]:
    """Convert raw voice text into a structured task manifest."""
    task_type = "general"
    zone      = "docs"

    for pattern, z, tt in _INTENT_RULES:
        if pattern.search(text):
            zone      = z
            task_type = tt
            break

    return {
        "id":         str(uuid.uuid4()),
        "task_type":  task_type,
        "zone":       zone,
        "source":     "voice_command",
        "content":    text.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status":     "pending",
    }


# ── Vault writer ───────────────────────────────────────────────────────────────

def _write_vault_task(task: dict[str, Any]) -> Path:
    voice_dir = _vault_dir() / "Needs_Action" / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    ts       = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"voice_{ts}_{task['id'][:8]}.json"
    dest     = voice_dir / filename
    tmp      = voice_dir / f".tmp_{filename}"

    tmp.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(dest)
    return dest


# ── Evidence log ───────────────────────────────────────────────────────────────

def _log_evidence(command: str, task: dict, dest: Path, mode: str) -> None:
    ev_dir = _evidence_dir()
    ev_dir.mkdir(parents=True, exist_ok=True)
    log_path = ev_dir / "VOICE_COMMAND_LOG.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(
            f"\n### {ts} — Voice Command ({mode})\n"
            f"- **Raw command:** \"{command}\"\n"
            f"- **Parsed type:** `{task['task_type']}`\n"
            f"- **Zone:** `{task['zone']}`\n"
            f"- **Task ID:** `{task['id']}`\n"
            f"- **Vault file:** `{dest.name}`\n"
        )


# ── Speech recognition backend ────────────────────────────────────────────────

def _mic_available() -> bool:
    try:
        import speech_recognition  # noqa: F401
        import pyaudio             # noqa: F401
        return True
    except ImportError:
        return False


def _listen_once(timeout: float = 5.0) -> str | None:
    """Capture one voice utterance from the microphone. Returns text or None."""
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            log.info("[voice] Adjusting for ambient noise…")
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            log.info("[voice] Listening (timeout=%.0fs)…", timeout)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=15)
        text = recognizer.recognize_google(audio)
        return text
    except Exception as exc:
        log.info("[voice] Recognition failed: %s", exc)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def process_command(text: str, mode: str = "text") -> Path:
    """Parse a command string and write it to the vault. Returns the task file path."""
    task = _parse_command(text)
    dest = _write_vault_task(task)
    _log_evidence(text, task, dest, mode)
    log.info("[voice] '%s' → %s (%s)", text[:60], dest.name, task["task_type"])
    return dest


def run_mic_loop(once: bool = False) -> None:
    """Continuous microphone listening loop."""
    if not _mic_available():
        log.warning("[voice] SpeechRecognition/PyAudio not installed; use --stdin or --text")
        return

    log.info("[voice] Microphone mode — say a command")
    while True:
        text = _listen_once()
        if text:
            process_command(text, mode="microphone")
            if once:
                break
        elif once:
            log.info("[voice] No speech detected")
            break
        time.sleep(0.5)


def run_stdin_loop(once: bool = False) -> None:
    """Read commands from stdin (one per line)."""
    import sys
    log.info("[voice] stdin mode — type a command and press Enter")
    for line in sys.stdin:
        text = line.strip()
        if text:
            process_command(text, mode="stdin")
            if once:
                break


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-8s %(message)s")
    parser = argparse.ArgumentParser(description="AI Vault Voice Command Interface")
    parser.add_argument("--once",  action="store_true", help="Process one command then exit")
    parser.add_argument("--stdin", action="store_true", help="Read commands from stdin")
    parser.add_argument("--text",  default=None,        help="Process a text command directly")
    args = parser.parse_args()

    if args.text:
        dest = process_command(args.text, mode="cli_text")
        print(f"[voice] Task written → {dest}")
    elif args.stdin:
        run_stdin_loop(once=args.once)
    else:
        if _mic_available():
            run_mic_loop(once=args.once)
        else:
            print("[voice] Microphone not available. Use --stdin or --text.")
            print("        Install: pip install SpeechRecognition pyaudio")
