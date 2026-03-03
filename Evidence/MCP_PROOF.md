# MCP Proof (Router + Registry)

This proof note explains how MCP dispatch works in this repo and how to
generate a saved MCP health report under `Evidence/`.

## 1) Router Usage (`mcp/router.py`)

`mcp/router.py` exposes `dispatch_action(action_type, payload)` as the MCP
dispatch entrypoint.

Flow:
1. `_load_stubs()` imports all MCP stub modules once.
2. Imported stubs self-register handlers in `mcp.registry`.
3. `dispatch_action(...)` resolves handler using `get_handler(action_type)`.
4. Handler executes with `dry_run=DRY_RUN`.
5. Result is returned as dict; router logs success/failure via `audit_logger`.

Key file:
- `mcp/router.py`

## 2) Registry Usage (`mcp/registry.py`)

`mcp/registry.py` is the central in-process mapping:
- `register(action_type, server_name, handler)` stores handler.
- `get_handler(action_type)` returns callable for dispatch.
- `list_registered()` returns `action_type -> server_name` snapshot.

Important behavior:
- `DRY_RUN` is controlled by `MCP_DRY_RUN` env var.
- Lazy autoload can import `mcp.router` and trigger stub loading if registry is empty.

Key file:
- `mcp/registry.py`

## 3) All MCP Stub/Server Modules (current repo)

- `mcp/email_mcp_stub.py`
  - Email draft/send stub actions for approval-safe flows.
- `mcp/browser_mcp_stub.py`
  - Browser navigation/extract stubs (non-destructive).
- `mcp/calendar_mcp_stub.py`
  - Calendar event create/update stub actions.
- `mcp/gmail_mcp_server.py`
  - Gmail-specific server overrides for email alias actions.
- `mcp/playwright_browser_server.py`
  - Playwright-backed browser server wrapper for web automation actions.
- `mcp/odoo_mcp_stub.py`
  - Odoo partner/invoice draft stubs with dry-run safe behavior.
- `mcp/social_mcp_stub.py`
  - Social post/schedule stubs (Twitter/Instagram/Facebook style actions).

## 4) Generate MCP Health Report (saved under Evidence)

Run from project root:

```bash
python tools/mcp_health_report.py
```

Saved output file:
- `Evidence/MCP_HEALTH_REPORT.json`

Optional (save console output too):

```powershell
python tools/mcp_health_report.py | Tee-Object -FilePath Evidence/MCP_HEALTH_REPORT.stdout.txt
```

## 5) Recommended Proof Artifacts

1. Screenshot of running command `python tools/mcp_health_report.py`
2. Screenshot showing generated file `Evidence/MCP_HEALTH_REPORT.json`
3. Screenshot opening `Evidence/MCP_HEALTH_REPORT.json` and showing:
   - `registered_tools`
   - `mcp_dry_run`
   - `health_status`
