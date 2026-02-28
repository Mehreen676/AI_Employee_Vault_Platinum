"""
Gold Tier Audit Logger – JSON-per-action logging to /Logs + Neon DB.

Every MCP tool call, agent decision, and error is logged as:
  1. A separate JSON file in /Logs (always)
  2. A row in the Neon DB 'events' table (if DATABASE_URL is set)

Never crashes on logging failures — falls back to stdout.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "Logs"

# ---- DB integration (optional) ----
_db_ok = False
_SessionLocal = None
_Event = None

try:
    from backend.db import db_available, SessionLocal
    from backend.models import Event
    if db_available and SessionLocal is not None:
        _db_ok = True
        _SessionLocal = SessionLocal
        _Event = Event
except Exception:
    pass

# Global run_id set by gold_agent at startup
_current_run_id: int | None = None


def set_run_id(run_id: int) -> None:
    """Called once by gold_agent after inserting the agent_runs row."""
    global _current_run_id
    _current_run_id = run_id


def get_db_event_count() -> int:
    """Return how many events were written for the current run_id."""
    if not _db_ok or _SessionLocal is None or _current_run_id is None:
        return 0
    try:
        session = _SessionLocal()
        try:
            count = session.query(_Event).filter(_Event.run_id == _current_run_id).count()
            return count
        finally:
            session.close()
    except Exception:
        return 0


def log_action(
    server: str,
    action: str,
    details: dict | None = None,
    success: bool = True,
) -> str:
    """Write one audit log entry to /Logs (JSON file) + DB. Returns filename."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    log_id = uuid.uuid4().hex[:12]
    filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{log_id}.json"

    entry = {
        "id": log_id,
        "timestamp": now.isoformat(),
        "server": server,
        "action": action,
        "details": details or {},
        "success": success,
    }

    # 1. JSON file (always)
    log_path = LOGS_DIR / filename
    try:
        log_path.write_text(json.dumps(entry, indent=2, default=str), encoding="utf-8")
    except Exception:
        print(f"[AUDIT FALLBACK] {json.dumps(entry, default=str)}")

    # 2. Neon DB (if available)
    if _db_ok and _SessionLocal is not None and _Event is not None:
        try:
            session = _SessionLocal()
            try:
                event_type = f"{server}.{action}"
                payload = json.dumps(entry, default=str)
                row = _Event(
                    run_id=_current_run_id,
                    event_type=event_type,
                    payload_json=payload,
                )
                session.add(row)
                session.commit()
            finally:
                session.close()
        except Exception:
            # Never crash on DB write failure
            pass

    return filename
