"""
MCP Server 4 – Audit & Compliance Operations.

Provides audit trail queries, compliance checks, and reporting.
Reads from /Logs JSON files for Gold tier accountability.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from audit_logger import log_action

SERVER_NAME = "mcp_audit_ops"
BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "Logs"


def get_recent_actions(hours: int = 24) -> list[dict]:
    """Return all audit log entries from the last N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    entries = []

    if not LOGS_DIR.is_dir():
        return entries

    for log_file in sorted(LOGS_DIR.glob("*.json")):
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue  # skip daily array logs (vault_logger format)
            ts = datetime.fromisoformat(data.get("timestamp", ""))
            if ts >= cutoff:
                entries.append(data)
        except (json.JSONDecodeError, ValueError, OSError):
            continue

    log_action(SERVER_NAME, "get_recent_actions", {"hours": hours, "count": len(entries)})
    return entries


def get_error_log(hours: int = 24) -> list[dict]:
    """Return failed actions from the last N hours."""
    all_actions = get_recent_actions(hours)
    errors = [a for a in all_actions if not a.get("success", True)]
    return errors


def get_action_summary(hours: int = 24) -> dict:
    """Return summary counts of actions by server and type."""
    actions = get_recent_actions(hours)
    summary: dict[str, int] = {}

    for action in actions:
        server = action.get("server", "unknown")
        action_type = action.get("action", "unknown")
        key = f"{server}.{action_type}"
        summary[key] = summary.get(key, 0) + 1

    result = {
        "total_actions": len(actions),
        "breakdown": summary,
        "errors": sum(1 for a in actions if not a.get("success", True)),
    }
    log_action(SERVER_NAME, "get_action_summary", {"hours": hours})
    return result


def compliance_check() -> dict:
    """Run a compliance check on the vault state."""
    base = Path(__file__).resolve().parent
    checks = {
        "env_file_not_tracked": not (base / ".env").exists() or ".env" in (base / ".gitignore").read_text(),
        "logs_dir_exists": LOGS_DIR.is_dir(),
        "gitignore_exists": (base / ".gitignore").exists(),
        "no_credentials_in_repo": not (base / "credentials.json").exists(),
        "no_token_in_repo": not (base / "token.json").exists(),
    }
    all_pass = all(checks.values())
    checks["all_pass"] = all_pass
    log_action(SERVER_NAME, "compliance_check", checks)
    return checks


if __name__ == "__main__":
    print(f"=== {SERVER_NAME} Server Ready ===")
    print("Tools: get_recent_actions, get_error_log, get_action_summary, compliance_check")
