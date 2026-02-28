"""
mcp/browser_mcp_stub.py — Browser & High-Risk Action MCP Stub (Gold Tier).

Handles HITL-approved actions that involve browser automation, payments,
deployments, destructive operations, or authorization requests.

DRY_RUN=true (default)
    Logs full intent and context but takes no real action.
    All 6 action types are registered; all log safely and return dry_run_logged.

DRY_RUN=false
    Real implementation placeholders — replace the TODO blocks per action type.

Registered action_types
-----------------------
    browser_action  — form submission, click confirm, auto-click
    authorize       — authorize transaction or access grant
    publish         — post/broadcast/announce content
    deploy          — push to production, go-live, release
    delete          — delete all, purge, drop table
    payment         — wire transfer, invoice pay, card charge, purchase

Environment variables (optional, only needed when DRY_RUN=false)
----------------------------------------------------------------
    PLAYWRIGHT_BROWSER   "chromium" | "firefox" | "webkit"
    DEPLOY_TARGET        Deployment target URL or identifier
    STRIPE_API_KEY       Stripe key for payment actions
    DB_ADMIN_URL         Admin DB URL for destructive delete actions
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from audit_logger import log_action
from mcp.registry import register

SERVER_NAME = "browser_mcp_stub"

# Descriptive label for each action type (used in log messages)
_ACTION_LABELS: dict[str, str] = {
    "browser_action":        "Browser interaction (submit form / click confirm / auto-click)",
    "browser_navigate_click":"Browser navigation + element click (URL + CSS selector / XPath)",
    "authorize":             "Authorization of transaction or access request",
    "publish":               "Content publication (post / broadcast / announce)",
    "deploy":                "Production deployment (push to prod / go-live / release)",
    "delete":                "Destructive deletion (delete all / purge / drop table)",
    "payment":               "Payment processing (wire transfer / invoice / card charge)",
}

# Real-implementation hints shown in TODO blocks
_ACTION_TODO_HINTS: dict[str, str] = {
    "browser_action": (
        "# Playwright example:\n"
        "#   from playwright.sync_api import sync_playwright\n"
        "#   with sync_playwright() as p:\n"
        "#       browser = p.chromium.launch()\n"
        "#       page = browser.new_page()\n"
        "#       page.goto(target_url)\n"
        "#       page.click(selector)\n"
        "#       browser.close()\n"
    ),
    "browser_navigate_click": (
        "# Playwright navigate + click example:\n"
        "#   from playwright.sync_api import sync_playwright\n"
        "#   with sync_playwright() as p:\n"
        "#       browser = p.chromium.launch()\n"
        "#       page = browser.new_page()\n"
        "#       page.goto(payload.get('url', ''))\n"
        "#       page.click(payload.get('selector', 'button'))\n"
        "#       browser.close()\n"
    ),
    "authorize": (
        "# Call your auth API / approval system:\n"
        "#   import requests\n"
        "#   resp = requests.post(auth_endpoint, json={...})\n"
    ),
    "publish": (
        "# CMS / social API publish:\n"
        "#   import requests\n"
        "#   requests.post(cms_publish_url, json={content, channel})\n"
    ),
    "deploy": (
        "# Deployment API (Heroku / k8s / Railway):\n"
        "#   import subprocess\n"
        "#   subprocess.run(['kubectl', 'apply', '-f', manifest], check=True)\n"
    ),
    "delete": (
        "# DB delete (use with extreme caution):\n"
        "#   from sqlalchemy import text\n"
        "#   session.execute(text('DELETE FROM table WHERE ...'))\n"
        "#   session.commit()\n"
    ),
    "payment": (
        "# Stripe payment example:\n"
        "#   import stripe\n"
        "#   stripe.api_key = os.getenv('STRIPE_API_KEY')\n"
        "#   stripe.PaymentIntent.create(amount=..., currency='usd')\n"
    ),
}


# ── Handler factory ───────────────────────────────────────────────────────────

def _make_handler(action_type: str):
    """
    Return a handler function for the given action_type.

    Using a factory avoids the loop-variable-capture closure bug —
    each returned function captures its own action_type correctly.
    """
    label = _ACTION_LABELS[action_type]
    todo_hint = _ACTION_TODO_HINTS[action_type]

    def handler(payload: dict, dry_run: bool = True) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        task_file = payload.get("task_file", payload.get("task_name", "unknown"))
        domain = payload.get("domain", "business")

        if dry_run:
            result: dict = {
                "server": SERVER_NAME,
                "action_type": action_type,
                "dry_run": True,
                "result": "dry_run_logged",
                "message": f"[DRY RUN] Would execute {action_type!r} — {label}",
                "timestamp": now,
                "intent": {
                    "action_type": action_type,
                    "task_file": task_file,
                    "domain": domain,
                    "label": label,
                },
            }
            log_action(SERVER_NAME, f"{action_type}_dry_run", {
                "action_type": action_type,
                "task_file": task_file,
                "domain": domain,
                "dry_run": True,
                "note": "Set MCP_DRY_RUN=false to enable real actions.",
            })
            print(f"  [{SERVER_NAME}] DRY RUN: {label}")
            print(f"  [{SERVER_NAME}]   action_type: {action_type}")
            print(f"  [{SERVER_NAME}]   task_file:   {task_file}")
            print(f"  [{SERVER_NAME}]   domain:      {domain}")
            print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable real execution.")

        else:
            # ── TODO: Replace with real implementation ────────────────────────
            # See implementation hint below for this action_type:
            # {todo_hint}
            # ─────────────────────────────────────────────────────────────────
            result = {
                "server": SERVER_NAME,
                "action_type": action_type,
                "dry_run": False,
                "result": "not_implemented",
                "message": (
                    f"Real {action_type!r} handler not yet implemented. "
                    "See the TODO block in browser_mcp_stub.py."
                ),
                "timestamp": now,
            }
            log_action(SERVER_NAME, f"{action_type}_not_implemented", {
                "action_type": action_type,
                "task_file": task_file,
            }, success=False)
            print(
                f"  [{SERVER_NAME}] WARN: Real {action_type!r} not implemented "
                "(see TODO in browser_mcp_stub.py)."
            )

        return result

    handler.__name__ = f"handle_{action_type}"
    handler.__qualname__ = f"browser_mcp_stub.handle_{action_type}"
    return handler


# ── Self-registration (runs at import time) ───────────────────────────────────

for _action_type in _ACTION_LABELS:
    register(_action_type, SERVER_NAME, _make_handler(_action_type))
