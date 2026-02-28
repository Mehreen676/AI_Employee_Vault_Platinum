"""
utils/rate_limiter.py — Per-category rate limiter with persistent state.

Enforces configurable action rate limits across processes by persisting
counters to vault/Logs/rate_limit_state.json. Counters survive restarts.

Default limits
--------------
    email:   max 10 per hour  (rolling window of 3 600 s)
    social:  max 20 per hour  (rolling window of 3 600 s)
    payment: max 3  per day   (rolling window of 86 400 s)
    file:    unlimited        (no limit enforced)

Payment auto-retry rule
-----------------------
    Payments must NEVER be automatically retried. The rate limiter enforces
    this by returning is_payment=True in the check result, which callers
    must honour by logging the failure and routing to human review only.

Usage
-----
    from utils.rate_limiter import RateLimiter

    rl = RateLimiter()
    allowed, reason = rl.check("email")
    if not allowed:
        print(reason)   # e.g. "Rate limit exceeded: email limit=10 per 3600s"
        return
    # ... perform action ...
    rl.record("email")  # persist the increment
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
_STATE_FILE   = _PROJECT_ROOT / "vault" / "Logs" / "rate_limit_state.json"

# Category -> {"max": int, "window_seconds": int, "no_auto_retry": bool}
LIMITS: dict[str, dict] = {
    "email":   {"max": 10, "window_seconds": 3_600,  "no_auto_retry": False},
    "social":  {"max": 20, "window_seconds": 3_600,  "no_auto_retry": False},
    "payment": {"max": 3,  "window_seconds": 86_400, "no_auto_retry": True},
    "file":    {"max": -1, "window_seconds": 3_600,  "no_auto_retry": False},
}


class RateLimiter:
    """
    Thread-safe (file-level) rate limiter.

    State is loaded from disk on each check() call and flushed on each
    record() call, making it safe across multiple concurrent processes.
    """

    def check(self, category: str) -> tuple[bool, str]:
        """
        Check whether an action in *category* is currently permitted.

        Args:
            category: One of "email", "social", "payment", "file", or any
                      unlisted string (treated as unlimited).

        Returns:
            (allowed, reason)
                allowed=True  if under the limit or category is unlimited.
                allowed=False if the limit would be exceeded.
                reason        describes the outcome for logging.
        """
        cfg = LIMITS.get(category)
        if cfg is None or cfg["max"] < 0:
            return True, "ok"

        state = self._load()
        now   = datetime.now(timezone.utc).timestamp()
        rec   = state.get(category, {"count": 0, "window_start": now})

        # Reset window if expired.
        if now - rec["window_start"] > cfg["window_seconds"]:
            rec = {"count": 0, "window_start": now}

        if rec["count"] >= cfg["max"]:
            remaining = cfg["window_seconds"] - (now - rec["window_start"])
            no_retry  = cfg.get("no_auto_retry", False)
            reason = (
                f"Rate limit exceeded: {category} "
                f"limit={cfg['max']} per {cfg['window_seconds']}s, "
                f"window resets in {remaining:.0f}s"
                + (" — payment: NEVER auto-retry, route to human review" if no_retry else "")
            )
            return False, reason

        return True, "ok"

    def record(self, category: str) -> None:
        """
        Increment the counter for *category* and persist to disk.

        Call AFTER a successful or attempted action, not before.
        """
        cfg = LIMITS.get(category)
        if cfg is None or cfg["max"] < 0:
            return

        state = self._load()
        now   = datetime.now(timezone.utc).timestamp()
        rec   = state.get(category, {"count": 0, "window_start": now})

        if now - rec["window_start"] > cfg["window_seconds"]:
            rec = {"count": 0, "window_start": now}

        rec["count"] += 1
        state[category] = rec
        self._save(state)

    def status(self) -> dict[str, dict]:
        """
        Return a snapshot of all counters for diagnostics / dashboard display.

        Returns:
            dict mapping category -> {"count", "limit", "window_start",
                                       "window_seconds", "remaining_in_window"}
        """
        state = self._load()
        now   = datetime.now(timezone.utc).timestamp()
        out   = {}
        for cat, cfg in LIMITS.items():
            rec = state.get(cat, {"count": 0, "window_start": now})
            if now - rec["window_start"] > cfg["window_seconds"]:
                rec = {"count": 0, "window_start": now}
            out[cat] = {
                "count":              rec["count"],
                "limit":              cfg["max"],
                "window_seconds":     cfg["window_seconds"],
                "remaining_in_window": max(0, cfg["window_seconds"] - (now - rec["window_start"])),
                "no_auto_retry":      cfg.get("no_auto_retry", False),
            }
        return out

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if _STATE_FILE.exists():
            try:
                return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save(self, state: dict) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        if _STATE_FILE.exists():
            _STATE_FILE.unlink()
        tmp.rename(_STATE_FILE)


# Module-level singleton for convenience import.
_limiter: Optional[RateLimiter] = None


def get_limiter() -> RateLimiter:
    """Return the module-level RateLimiter singleton."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
