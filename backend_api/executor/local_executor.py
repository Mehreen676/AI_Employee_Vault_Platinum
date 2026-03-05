"""
AI Employee Vault – Platinum Tier
Local Executor Heartbeat Worker

Module:  backend_api/executor/local_executor.py
Version: 1.0.0

Runs as a daemon thread inside the FastAPI process.
Every `interval` seconds writes a heartbeat record to:

    VAULT_LOG_DIR/local_executor_heartbeat.json

This keeps the Watchdog Health panel showing local_executor=online
as long as the backend process is alive.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


# ── Path resolver ──────────────────────────────────────────────────────────────

def _log_dir() -> Path:
    vault_dir = Path(os.getenv("VAULT_DIR",     "/tmp/vault"))
    return   Path(os.getenv("VAULT_LOG_DIR", str(vault_dir / "Logs")))


# ── Heartbeat writer ───────────────────────────────────────────────────────────

def _write_heartbeat(log_dir: Path) -> None:
    hb_path = log_dir / "local_executor_heartbeat.json"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        hb_path.write_text(
            json.dumps({
                "component": "local_executor",
                "status":    "online",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("[local_executor] heartbeat write failed: %s", exc)


# ── Main loop ──────────────────────────────────────────────────────────────────

def run_local_executor_loop(interval: float = 5.0) -> None:
    """
    Infinite heartbeat loop.  Run as a daemon thread:

        t = threading.Thread(target=run_local_executor_loop, daemon=True)
        t.start()
    """
    log.info("[local_executor] heartbeat loop started (interval=%.1fs)", interval)
    log_dir = _log_dir()
    while True:
        try:
            _write_heartbeat(log_dir)
        except Exception as exc:
            log.warning("[local_executor] unexpected error: %s", exc)
        time.sleep(interval)
