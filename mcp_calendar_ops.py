"""
MCP Server 3 – Calendar & Scheduling Operations.

Handles task scheduling, deadline tracking, and briefing schedule management.
Provides time-based task prioritization for Gold tier.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from audit_logger import log_action

SERVER_NAME = "mcp_calendar_ops"


def get_current_week() -> dict:
    """Return current week boundaries (Monday-Sunday) in UTC."""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    result = {
        "week_start": monday.strftime("%Y-%m-%d"),
        "week_end": sunday.strftime("%Y-%m-%d"),
        "current_day": now.strftime("%A"),
        "current_date": now.strftime("%Y-%m-%d"),
        "iso_week": now.isocalendar()[1],
    }
    log_action(SERVER_NAME, "get_current_week", result)
    return result


def is_briefing_due(last_briefing_date: str | None = None) -> bool:
    """Check if a weekly CEO briefing is due (every 7 days)."""
    if not last_briefing_date:
        return True
    try:
        last = datetime.strptime(last_briefing_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        due = (now - last).days >= 7
        log_action(SERVER_NAME, "is_briefing_due", {"last": last_briefing_date, "due": due})
        return due
    except ValueError:
        return True


def prioritize_tasks(tasks: list[dict]) -> list[dict]:
    """Sort tasks by priority: urgent > business > personal > low."""
    priority_map = {"urgent": 0, "business": 1, "personal": 2, "low": 3}

    def sort_key(task: dict) -> int:
        return priority_map.get(task.get("priority", "low"), 3)

    sorted_tasks = sorted(tasks, key=sort_key)
    log_action(SERVER_NAME, "prioritize_tasks", {"count": len(tasks)})
    return sorted_tasks


def create_schedule_entry(task_name: str, domain: str, estimated_minutes: int = 30) -> dict:
    """Create a schedule entry for a task."""
    now = datetime.now(timezone.utc)
    entry = {
        "task": task_name,
        "domain": domain,
        "scheduled_at": now.isoformat(),
        "estimated_minutes": estimated_minutes,
        "deadline": (now + timedelta(minutes=estimated_minutes)).isoformat(),
    }
    log_action(SERVER_NAME, "create_schedule_entry", entry)
    return entry


if __name__ == "__main__":
    print(f"=== {SERVER_NAME} Server Ready ===")
    print("Tools: get_current_week, is_briefing_due, prioritize_tasks, create_schedule_entry")
