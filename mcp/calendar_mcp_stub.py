"""
mcp/calendar_mcp_stub.py — Calendar Action MCP Stub (Gold Tier).

Handles HITL-approved calendar and scheduling actions.

DRY_RUN=true (default)
    Logs full intent (title, start, end, attendees) but creates nothing.
    Safe for CI, staging, and all non-production environments.

DRY_RUN=false
    Real implementation placeholder — replace the TODO block with
    Google Calendar API calls (google-auth + googleapiclient).

Registered action_types
-----------------------
    create_calendar_event  — schedule meeting / create event / add to calendar

Environment variables (all optional, only needed when DRY_RUN=false)
--------------------------------------------------------------------
    GOOGLE_CALENDAR_ID    Target calendar ID (default: "primary")
    GOOGLE_CREDENTIALS    Path to service account credentials.json
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from audit_logger import log_action
from mcp.registry import register

SERVER_NAME = "calendar_mcp_stub"


def handle_create_calendar_event(payload: dict, dry_run: bool = True) -> dict:
    """
    Execute or simulate a create_calendar_event action.

    Expected payload keys (all optional):
        task_file    — originating task filename
        domain       — "business" or "personal"
        run_id       — agent run identifier
        title        — event title / summary
        start        — ISO datetime string for event start
        end          — ISO datetime string for event end
        attendees    — list of attendee email addresses
        location     — event location string
        description  — event body / notes
    """
    now = datetime.now(timezone.utc).isoformat()
    task_file = payload.get("task_file", payload.get("task_name", "unknown"))
    title = payload.get("title", f"AI Vault — Event for task: {task_file}")
    start = payload.get("start", "<not specified>")
    end = payload.get("end", "<not specified>")
    attendees = payload.get("attendees", [])
    calendar_id = payload.get("calendar_id", os.getenv("GOOGLE_CALENDAR_ID", "primary"))

    if dry_run:
        result: dict = {
            "server": SERVER_NAME,
            "action_type": "create_calendar_event",
            "dry_run": True,
            "result": "dry_run_logged",
            "message": (
                f"[DRY RUN] Would create calendar event — "
                f"task: {task_file!r}, title: {title!r}"
            ),
            "timestamp": now,
            "intent": {
                "calendar_id": calendar_id,
                "title": title,
                "start": start,
                "end": end,
                "attendees": attendees,
                "task_file": task_file,
            },
        }
        log_action(SERVER_NAME, "create_calendar_event_dry_run", {
            "task_file": task_file,
            "title": title,
            "start": start,
            "end": end,
            "attendees": attendees,
            "calendar_id": calendar_id,
            "dry_run": True,
            "note": "Set MCP_DRY_RUN=false to enable real calendar creates.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would create calendar event")
        print(f"  [{SERVER_NAME}]   Title:    {title}")
        print(f"  [{SERVER_NAME}]   Start:    {start}")
        print(f"  [{SERVER_NAME}]   End:      {end}")
        print(f"  [{SERVER_NAME}]   Calendar: {calendar_id}")
        print(f"  [{SERVER_NAME}]   Task:     {task_file}")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")

    else:
        # ── TODO: Replace with real Google Calendar implementation ─────────────
        # from google.oauth2 import service_account
        # from googleapiclient.discovery import build
        # creds = service_account.Credentials.from_service_account_file(
        #     os.getenv("GOOGLE_CREDENTIALS", "credentials.json"),
        #     scopes=["https://www.googleapis.com/auth/calendar"],
        # )
        # service = build("calendar", "v3", credentials=creds)
        # event = {
        #     "summary": title,
        #     "start": {"dateTime": start, "timeZone": "UTC"},
        #     "end":   {"dateTime": end,   "timeZone": "UTC"},
        #     "attendees": [{"email": a} for a in attendees],
        # }
        # created = service.events().insert(calendarId=calendar_id, body=event).execute()
        # ──────────────────────────────────────────────────────────────────────
        result = {
            "server": SERVER_NAME,
            "action_type": "create_calendar_event",
            "dry_run": False,
            "result": "not_implemented",
            "message": (
                "Real calendar event creation not yet implemented — "
                "replace TODO block in calendar_mcp_stub.py."
            ),
            "timestamp": now,
        }
        log_action(SERVER_NAME, "create_calendar_event_not_implemented", {
            "task_file": task_file,
        }, success=False)
        print(
            f"  [{SERVER_NAME}] WARN: Real calendar creation not implemented "
            "(see TODO in calendar_mcp_stub.py)."
        )

    return result


# ── Self-registration (runs at import time) ───────────────────────────────────

register("create_calendar_event", SERVER_NAME, handle_create_calendar_event)
