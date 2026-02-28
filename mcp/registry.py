"""
mcp/registry.py — MCP Tool Registry for Gold Tier.

Central in-process registry that maps action_type strings to handler functions.
Stubs self-register on import by calling register().

DRY_RUN (default True)
    True  → stubs log intent only; no real external actions taken.
    False → stubs attempt real implementations (most are still placeholders).

    Override at runtime:
        export MCP_DRY_RUN=false          # bash / GitHub Actions secret
        $env:MCP_DRY_RUN = "false"        # PowerShell

Lazy autoload
-------------
    If the registry is empty when list_registered() or get_handler() is called,
    and MCP_REGISTRY_AUTOLOAD != "false", the registry will automatically import
    mcp.router and trigger _load_stubs() so all stubs self-register.

    This means:
        from mcp.registry import list_registered
        print(len(list_registered()))   # prints real count, not 0

    Opt-out:  export MCP_REGISTRY_AUTOLOAD=false
    Debug:    export MCP_DEBUG=true   (prints full traceback on autoload failure)
"""

from __future__ import annotations

import importlib
import os
from typing import Callable

# ── DRY_RUN flag (read once at import time) ───────────────────────────────────
DRY_RUN: bool = os.getenv("MCP_DRY_RUN", "true").lower() != "false"

# ── Autoload config (read once at import time) ────────────────────────────────
_AUTOLOAD_ENABLED: bool = os.getenv("MCP_REGISTRY_AUTOLOAD", "true").lower() != "false"
_MCP_DEBUG: bool = os.getenv("MCP_DEBUG", "false").lower() == "true"

# ── Registry store ─────────────────────────────────────────────────────────────
# Maps action_type → (server_name, handler_callable)
_REGISTRY: dict[str, tuple[str, Callable]] = {}

# ── Autoload state ─────────────────────────────────────────────────────────────
_autoload_done: bool = False


def _autoload() -> None:
    """
    Lazily import mcp.router and trigger stub loading if the registry is empty.

    Safe to call multiple times — idempotent via _autoload_done flag.
    Never raises; prints traceback only when MCP_DEBUG=true.

    Flow:
        1. Import mcp.router (which at module-level only defines functions).
        2. Call router._load_stubs() to import all stub modules.
        3. Each stub calls register() for its action_types.
        4. _REGISTRY is now populated.
    """
    global _autoload_done
    if _autoload_done or not _AUTOLOAD_ENABLED:
        return

    # Mark done *before* the attempt to prevent re-entrant calls.
    _autoload_done = True

    try:
        router = importlib.import_module("mcp.router")
        load_fn = getattr(router, "_load_stubs", None)
        if callable(load_fn):
            load_fn()
    except Exception:  # noqa: BLE001
        if _MCP_DEBUG:
            import traceback
            traceback.print_exc()


def register(action_type: str, server_name: str, handler: Callable) -> None:
    """
    Register a handler for the given action_type.

    Called at module import time by each MCP stub.
    Later registrations silently overwrite earlier ones (last-writer wins),
    which lets gmail_mcp_server override the email_mcp_stub alias for
    send_email / draft_email.

    Args:
        action_type:  String key, e.g. "email_send", "publish", "payment".
        server_name:  Human-readable server label, e.g. "email_mcp_stub".
        handler:      Callable with signature handler(payload: dict, dry_run: bool) -> dict.
    """
    _REGISTRY[action_type] = (server_name, handler)


def get_handler(action_type: str) -> Callable | None:
    """
    Return the registered handler for action_type, or None if not found.

    Triggers lazy autoload if the registry is empty.

    Args:
        action_type:  String key to look up.

    Returns:
        handler callable, or None.
    """
    if not _REGISTRY:
        _autoload()
    entry = _REGISTRY.get(action_type)
    return entry[1] if entry else None


def list_registered() -> dict[str, str]:
    """
    Return a snapshot of all registered action_types → server_name mappings.

    Triggers lazy autoload if the registry is empty.

    Returns:
        dict mapping action_type → server_name.
    """
    if not _REGISTRY:
        _autoload()
    return {action_type: server_name for action_type, (server_name, _) in _REGISTRY.items()}
