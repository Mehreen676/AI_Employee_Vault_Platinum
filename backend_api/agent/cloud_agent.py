"""
AI Employee Vault – Platinum Tier
Cloud Agent Queue Processor

Module:  backend_api/agent/cloud_agent.py
Version: 1.0.0

Continuously moves tasks through the workflow:
    Needs_Action → Waiting_Approval → Done

Runs as a daemon thread inside the FastAPI process on both local and
HuggingFace Spaces.  All paths are resolved from VAULT_DIR at call time
so env-var overrides take effect correctly.

Loop behaviour (default interval = 5 s):
    Phase 1: Promote every file in Waiting_Approval  → Done
    Phase 2: Promote every file in Needs_Action      → Waiting_Approval
    Phase 3: Write heartbeat to Logs/agent_heartbeat.json

Files moved to Waiting_Approval in Phase 2 are NOT immediately promoted
to Done in the same tick — they wait at least one full interval first.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


# ── Path resolver ─────────────────────────────────────────────────────────────

def _dirs() -> dict[str, Path]:
    """Return all relevant paths, re-reading env vars every call."""
    vault_dir = Path(os.environ.get("VAULT_DIR", "/tmp/vault"))
    queue_dir = vault_dir / "Queue"
    log_dir   = Path(os.environ.get("VAULT_LOG_DIR", str(vault_dir / "Logs")))
    return {
        "needs_action":     queue_dir / "Needs_Action",
        "waiting_approval": queue_dir / "Waiting_Approval",
        "done":             queue_dir / "Done",
        "execution_log":    log_dir   / "execution_log.json",
        "prompt_chain":     log_dir   / "prompt_chain.json",
        "heartbeat":        log_dir   / "agent_heartbeat.json",
    }


# ── File helpers ──────────────────────────────────────────────────────────────

def _append_jsonl(path: Path, record: dict) -> None:
    """Append a single JSON record to a JSONL file, creating it if needed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("[cloud_agent] JSONL write failed %s: %s", path, exc)


def _write_heartbeat(path: Path) -> None:
    """Overwrite heartbeat file with current timestamp and running status."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "agent":     "cloud_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status":    "running",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("[cloud_agent] Heartbeat write failed: %s", exc)


def _safe_dest(dest_dir: Path, filename: str) -> Path:
    """
    Return a destination path that does not already exist.
    If <filename> is taken, append _1, _2, … until a free slot is found.
    """
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    stem   = Path(filename).stem
    suffix = Path(filename).suffix
    n = 1
    while True:
        candidate = dest_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _move_task(src: Path, dest_dir: Path, action: str, d: dict) -> None:
    """
    Read *src*, move it to *dest_dir*, then append log records.

    Args:
        src:      Source file path.
        dest_dir: Target queue directory.
        action:   Human-readable action label for the log.
        d:        Path dict from _dirs().
    """
    # Read task data BEFORE moving so we capture the id / task_type
    try:
        task_data: dict = json.loads(src.read_text(encoding="utf-8"))
    except Exception:
        task_data = {}

    dest = _safe_dest(dest_dir, src.name)

    try:
        shutil.move(str(src), str(dest))
    except OSError as exc:
        log.error("[cloud_agent] Move failed %s → %s: %s", src, dest, exc)
        return

    now = datetime.now(timezone.utc).isoformat()

    _append_jsonl(d["execution_log"], {
        "id":        task_data.get("id", src.stem),
        "task_type": task_data.get("task_type", "queue_transition"),
        "action":    action,
        "from":      src.parent.name,
        "to":        dest_dir.name,
        "filename":  dest.name,
        "timestamp": now,
        "source":    "cloud_agent",
    })

    _append_jsonl(d["prompt_chain"], {
        "timestamp":  now,
        "component":  "cloud_agent",
        "event_type": "task_executing",
        "content": {
            "summary": f"{action}: {src.name}",
            "detail":  f"{src.parent.name} → {dest_dir.name}",
        },
    })

    log.info(
        "[cloud_agent] %s  %s/%s  →  %s",
        action, src.parent.name, src.name, dest_dir.name,
    )


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_cloud_agent_loop(interval: float = 5.0) -> None:
    """
    Daemon loop — intended to run in a background thread.

    Each iteration:
        1. Phase 1 – Promote Waiting_Approval → Done
        2. Phase 2 – Promote Needs_Action     → Waiting_Approval
        3. Write heartbeat
        4. Sleep *interval* seconds

    Phase 1 runs before Phase 2 so files promoted in this tick do not
    immediately skip the Waiting_Approval stage.
    """
    log.info("[cloud_agent] Loop started (interval=%.1fs)", interval)

    while True:
        try:
            d = _dirs()

            # Ensure queue dirs exist
            for key in ("needs_action", "waiting_approval", "done"):
                try:
                    d[key].mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass

            # ── Phase 1: Waiting_Approval → Done ─────────────────────────────
            if d["waiting_approval"].exists():
                for f in sorted(d["waiting_approval"].iterdir()):
                    if f.is_file() and not f.name.startswith("."):
                        _move_task(f, d["done"], "approved_and_completed", d)

            # ── Phase 2: Needs_Action → Waiting_Approval ─────────────────────
            if d["needs_action"].exists():
                for f in sorted(d["needs_action"].iterdir()):
                    if f.is_file() and not f.name.startswith("."):
                        _move_task(f, d["waiting_approval"], "claimed_for_review", d)

            # ── Heartbeat ─────────────────────────────────────────────────────
            _write_heartbeat(d["heartbeat"])

        except Exception as exc:
            log.exception("[cloud_agent] Unhandled loop error: %s", exc)

        time.sleep(interval)
