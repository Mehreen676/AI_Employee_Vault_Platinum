"""
mcp/router.py — MCP Action Dispatcher for Gold Tier.

dispatch_action(action_type, payload) is the single entry point called by
gold_agent.py when a HITL-approved task resumes. The router:
  1. Auto-imports all stub modules so they self-register in the registry.
  2. Looks up the action_type in the registry.
  3. Calls the registered handler with (payload, dry_run=DRY_RUN).
  4. Logs the outcome via audit_logger.
  5. Never raises — always returns a result dict.

Adding a new stub
-----------------
  1. Create mcp/my_stub.py, call register() for each action_type it handles.
  2. Add the module path to _STUB_MODULES below.
  3. Add action_type entries to mcp.json (servers + action_routing sections).
  4. Document new action_types in mcp/__init__.py.
"""

from __future__ import annotations

import importlib

import audit_logger
from audit_logger import log_action
from mcp.registry import DRY_RUN, get_handler, list_registered

SERVER_NAME = "mcp_router"

# ── Stub modules to auto-import ───────────────────────────────────────────────
# Order matters only for alias overrides: later imports overwrite earlier ones.
# e.g. gmail_mcp_server registers "send_email" after email_mcp_stub does.
_STUB_MODULES: list[str] = [
    "mcp.email_mcp_stub",
    "mcp.browser_mcp_stub",
    "mcp.calendar_mcp_stub",
    "mcp.gmail_mcp_server",
    "mcp.playwright_browser_server",
    "mcp.odoo_mcp_stub",
    "mcp.social_mcp_stub",
]

_stubs_loaded = False


def _load_stubs() -> None:
    """Import all stub modules once so they self-register in the registry."""
    global _stubs_loaded
    if _stubs_loaded:
        return
    for module_path in _STUB_MODULES:
        try:
            importlib.import_module(module_path)
        except Exception as exc:
            print(f"  [mcp_router] WARN: could not load stub {module_path!r}: {exc}")
    _stubs_loaded = True


def dispatch_action(action_type: str, payload: dict) -> dict:
    """
    Dispatch an approved MCP action to its registered handler.

    Args:
        action_type:  String key, e.g. "email_send", "publish", "social_post_twitter".
        payload:      Arbitrary dict passed verbatim to the handler.

    Returns:
        Result dict from the handler, always including at least:
            {"server": ..., "action_type": ..., "result": ..., "dry_run": ...}
        On failure/unknown, returns an error dict (never raises).
    """
    _load_stubs()

    handler = get_handler(action_type)

    if handler is None:
        registered = list_registered()
        err = {
            "server": SERVER_NAME,
            "action_type": action_type,
            "dry_run": DRY_RUN,
            "result": "error_not_registered",
            "message": (
                f"No handler registered for action_type={action_type!r}. "
                f"Registered types: {sorted(registered.keys())}"
            ),
        }
        log_action(SERVER_NAME, "dispatch_error_not_registered", {
            "action_type": action_type,
            "registered_count": len(registered),
        }, success=False)
        print(f"  [mcp_router] ERROR: unknown action_type={action_type!r}")
        return err

    try:
        result = handler(payload, dry_run=DRY_RUN)
        log_action(SERVER_NAME, f"dispatch_ok.{action_type}", {
            "action_type": action_type,
            "dry_run": DRY_RUN,
            "result": result.get("result"),
        })
        return result
    except Exception as exc:
        err = {
            "server": SERVER_NAME,
            "action_type": action_type,
            "dry_run": DRY_RUN,
            "result": "error_handler_exception",
            "message": str(exc),
        }
        log_action(SERVER_NAME, f"dispatch_error.{action_type}", {
            "action_type": action_type,
            "error": str(exc),
        }, success=False)
        print(f"  [mcp_router] ERROR in handler for {action_type!r}: {exc}")
        return err
