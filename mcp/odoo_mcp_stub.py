"""
mcp/odoo_mcp_stub.py — Real Odoo 19 Community JSON-RPC MCP integration (Gold Tier).

Wraps odoo_client.OdooClient as MCP tool handlers so HITL-approved Odoo
actions can be dispatched through the standard mcp.router.dispatch_action()
entry point.

Every JSON-RPC request and response is written as a structured JSON file in
Logs/ via audit_logger.log_action() — one file per action.

DRY_RUN=true (default, controlled by MCP_DRY_RUN env var)
    Logs full intent to audit_logger + Logs/<timestamp>.json.
    No network call to Odoo is made.
    Safe for CI, staging, and agents without an Odoo instance.

DRY_RUN=false
    Real JSON-RPC calls via odoo_client.OdooClient.from_env().
    Requires ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD in .env.

Registered action_types
-----------------------
    odoo_create_partner    Create a res.partner contact record.
    odoo_create_invoice    Create an out_invoice (account.move) record.
    odoo_list_invoices     search_read invoices with optional filter.

Environment variables (required only when MCP_DRY_RUN=false)
------------------------------------------------------------
    ODOO_URL        Base URL of your Odoo instance (http://localhost:8069)
    ODOO_DB         Database name
    ODOO_USERNAME   Login username / email (ODOO_USER also accepted)
    ODOO_PASSWORD   User password or API key

See docs/ODOO_SETUP.md for step-by-step setup instructions.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from audit_logger import log_action
from mcp.registry import register

SERVER_NAME = "odoo_mcp_stub"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_client():
    """Import and instantiate OdooClient from env. Raises OdooError on failure."""
    from odoo_client import OdooClient
    return OdooClient.from_env()


def _error_result(action_type: str, dry_run: bool, message: str, task_file: str) -> dict:
    return {
        "server":      SERVER_NAME,
        "action_type": action_type,
        "dry_run":     dry_run,
        "result":      "error",
        "task_file":   task_file,
        "message":     message,
        "timestamp":   _now(),
    }


# ── Handlers ──────────────────────────────────────────────────────────────────

def handle_odoo_create_partner(payload: dict, dry_run: bool = True) -> dict:
    """
    Create a res.partner contact in Odoo.

    Required payload keys:
        name        Contact full name

    Optional payload keys:
        email       Email address
        phone       Phone number
        company     Company name
        task_file   Originating task filename (audit logging)
    """
    task_file = payload.get("task_file", payload.get("task_name", "unknown"))
    name      = payload.get("name", "")
    email     = payload.get("email", "")
    phone     = payload.get("phone", "")
    company   = payload.get("company", "")

    if dry_run:
        result: dict = {
            "server":      SERVER_NAME,
            "action_type": "odoo_create_partner",
            "dry_run":     True,
            "result":      "dry_run_logged",
            "message":     f"[DRY RUN] Would create Odoo partner: name={name!r}, email={email!r}",
            "timestamp":   _now(),
            "intent": {
                "name": name, "email": email,
                "phone": phone, "company": company,
                "task_file": task_file,
            },
        }
        log_action(SERVER_NAME, "odoo_create_partner_dry_run", {
            "action_type": "odoo_create_partner",
            "request":     {"name": name, "email": email, "phone": phone, "company": company},
            "response":    "dry_run — no network call",
            "task_file":   task_file,
            "dry_run":     True,
            "note":        "Set MCP_DRY_RUN=false + ODOO_* env vars for real execution.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would create Odoo partner: {name!r}")
        return result

    # ── Real JSON-RPC call ──
    request_details = {
        "action_type": "odoo_create_partner",
        "rpc_method":  "res.partner/create",
        "request":     {"name": name, "email": email, "phone": phone, "company": company},
        "task_file":   task_file,
        "dry_run":     False,
    }
    try:
        client     = _get_client()
        partner_id = client.create_partner_stub(
            name=name,
            email=email or "",
            phone=phone or "",
            company=company or "",
        )
        response = {"partner_id": partner_id, "status": "created"}
        result = {
            "server":      SERVER_NAME,
            "action_type": "odoo_create_partner",
            "dry_run":     False,
            "result":      "created",
            "partner_id":  partner_id,
            "message":     f"Created Odoo partner: id={partner_id}, name={name!r}",
            "timestamp":   _now(),
        }
        log_action(SERVER_NAME, "odoo_create_partner_ok", {
            **request_details,
            "response": response,
        })
        print(f"  [{SERVER_NAME}] Created Odoo partner: id={partner_id}, name={name!r}")
        return result
    except Exception as exc:
        log_action(SERVER_NAME, "odoo_create_partner_error", {
            **request_details,
            "response": {"error": str(exc)},
        }, success=False)
        print(f"  [{SERVER_NAME}] ERROR creating Odoo partner: {exc}")
        return _error_result("odoo_create_partner", False, str(exc), task_file)


def handle_odoo_create_invoice(payload: dict, dry_run: bool = True) -> dict:
    """
    Create a customer invoice (account.move, move_type='out_invoice') in Odoo.

    Required payload keys:
        partner_id    res.partner database ID to bill

    Optional payload keys:
        lines         List of line dicts:  [{name, quantity, price_unit}, ...]
                      Defaults to a single placeholder line if omitted.
        currency      ISO 4217 currency code (default: "USD")
        ref           Customer / vendor reference string
        task_file     Originating task filename (audit logging)
    """
    task_file  = payload.get("task_file", payload.get("task_name", "unknown"))
    partner_id = payload.get("partner_id")
    lines      = payload.get("lines", [{"name": "Service fee", "quantity": 1, "price_unit": 0.0}])
    currency   = payload.get("currency", "USD")
    ref        = payload.get("ref", "")

    if dry_run:
        total = sum(
            float(l.get("quantity", 1)) * float(l.get("price_unit", 0))
            for l in lines
        )
        result: dict = {
            "server":      SERVER_NAME,
            "action_type": "odoo_create_invoice",
            "dry_run":     True,
            "result":      "dry_run_logged",
            "message": (
                f"[DRY RUN] Would create Odoo invoice: partner_id={partner_id}, "
                f"lines={len(lines)}, total={total} {currency}"
            ),
            "timestamp": _now(),
            "intent": {
                "partner_id": partner_id, "lines_count": len(lines),
                "currency": currency, "ref": ref, "task_file": task_file,
            },
        }
        log_action(SERVER_NAME, "odoo_create_invoice_dry_run", {
            "action_type": "odoo_create_invoice",
            "request":     {"partner_id": partner_id, "lines": lines, "currency": currency, "ref": ref},
            "response":    "dry_run — no network call",
            "task_file":   task_file,
            "dry_run":     True,
            "note":        "Set MCP_DRY_RUN=false + ODOO_* env vars for real execution.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would create Odoo invoice for partner_id={partner_id}")
        return result

    # ── Real JSON-RPC call ──
    request_details = {
        "action_type": "odoo_create_invoice",
        "rpc_method":  "account.move/create",
        "request":     {"partner_id": partner_id, "lines": lines, "currency": currency, "ref": ref},
        "task_file":   task_file,
        "dry_run":     False,
    }
    try:
        client     = _get_client()
        invoice_id = client.create_invoice_stub(
            partner_id=int(partner_id),
            lines=lines,
            currency_code=currency,
            ref=ref or "",
        )
        response = {"invoice_id": invoice_id, "status": "created"}
        result = {
            "server":      SERVER_NAME,
            "action_type": "odoo_create_invoice",
            "dry_run":     False,
            "result":      "created",
            "invoice_id":  invoice_id,
            "message":     f"Created Odoo invoice: id={invoice_id}, partner_id={partner_id}",
            "timestamp":   _now(),
        }
        log_action(SERVER_NAME, "odoo_create_invoice_ok", {
            **request_details,
            "response": response,
        })
        print(f"  [{SERVER_NAME}] Created Odoo invoice: id={invoice_id}")
        return result
    except Exception as exc:
        log_action(SERVER_NAME, "odoo_create_invoice_error", {
            **request_details,
            "response": {"error": str(exc)},
        }, success=False)
        print(f"  [{SERVER_NAME}] ERROR creating Odoo invoice: {exc}")
        return _error_result("odoo_create_invoice", False, str(exc), task_file)


def handle_odoo_list_invoices(payload: dict, dry_run: bool = True) -> dict:
    """
    Search and return invoices from Odoo (account.move).

    Optional payload keys:
        limit       Max records to return (default: 10)
        state       Filter by state: "draft" | "posted" | "cancel"
        move_types  List of move_type strings
                    (default: ["out_invoice", "in_invoice"])
        task_file   Originating task filename (audit logging)
    """
    task_file  = payload.get("task_file", payload.get("task_name", "unknown"))
    limit      = int(payload.get("limit", 10))
    state      = payload.get("state", "")
    move_types = payload.get("move_types", ["out_invoice", "in_invoice"])

    if dry_run:
        result: dict = {
            "server":      SERVER_NAME,
            "action_type": "odoo_list_invoices",
            "dry_run":     True,
            "result":      "dry_run_logged",
            "message": (
                f"[DRY RUN] Would list Odoo invoices: limit={limit}, "
                f"state={state!r}, move_types={move_types}"
            ),
            "timestamp": _now(),
            "intent": {
                "limit": limit, "state": state,
                "move_types": move_types, "task_file": task_file,
            },
        }
        log_action(SERVER_NAME, "odoo_list_invoices_dry_run", {
            "action_type": "odoo_list_invoices",
            "request":     {"limit": limit, "state": state, "move_types": move_types},
            "response":    "dry_run — no network call",
            "task_file":   task_file,
            "dry_run":     True,
            "note":        "Set MCP_DRY_RUN=false + ODOO_* env vars for real execution.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would list Odoo invoices (limit={limit})")
        return result

    # ── Real JSON-RPC call ──
    request_details = {
        "action_type": "odoo_list_invoices",
        "rpc_method":  "account.move/search_read",
        "request":     {"limit": limit, "state": state or None, "move_types": move_types},
        "task_file":   task_file,
        "dry_run":     False,
    }
    try:
        client   = _get_client()
        invoices = client.list_invoices(
            limit=limit,
            state=state or None,
            move_types=move_types,
        )
        response = {"count": len(invoices), "invoices": invoices}
        result = {
            "server":      SERVER_NAME,
            "action_type": "odoo_list_invoices",
            "dry_run":     False,
            "result":      "ok",
            "count":       len(invoices),
            "invoices":    invoices,
            "message":     f"Listed {len(invoices)} Odoo invoices",
            "timestamp":   _now(),
        }
        log_action(SERVER_NAME, "odoo_list_invoices_ok", {
            **request_details,
            "response": response,
        })
        print(f"  [{SERVER_NAME}] Listed {len(invoices)} Odoo invoices")
        return result
    except Exception as exc:
        log_action(SERVER_NAME, "odoo_list_invoices_error", {
            **request_details,
            "response": {"error": str(exc)},
        }, success=False)
        print(f"  [{SERVER_NAME}] ERROR listing Odoo invoices: {exc}")
        return _error_result("odoo_list_invoices", False, str(exc), task_file)


# ── Self-registration (runs at import time) ───────────────────────────────────

register("odoo_create_partner", SERVER_NAME, handle_odoo_create_partner)
register("odoo_create_invoice", SERVER_NAME, handle_odoo_create_invoice)
register("odoo_list_invoices",  SERVER_NAME, handle_odoo_list_invoices)
