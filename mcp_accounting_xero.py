"""
MCP Accounting – Xero Integration Stub.

Simulates invoice creation via the Xero API.
No real credentials required — all calls are dry-run stubs with full audit logging.

Usage:
    tool = AccountingXeroTool()
    result = tool.create_invoice("Acme Corp", 1500.00)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from audit_logger import log_action

SERVER_NAME   = "mcp_accounting_xero"
BASE_DIR      = Path(__file__).resolve().parent
LOGS_DIR      = BASE_DIR / "Logs"
ACCOUNTING_LOG = LOGS_DIR / "accounting.json"

# Invoice counter — increments per process lifetime; resets on restart.
# In production replace with a DB sequence or Xero's returned invoice number.
_invoice_counter: int = 0

# Stub: replace with real Xero OAuth2 credentials
_XERO_CLIENT_ID     = ""
_XERO_CLIENT_SECRET = ""
_XERO_TENANT_ID     = ""


class AccountingXeroTool:
    """MCP tool for Xero accounting operations (stub — no real credentials required)."""

    def create_invoice(self, customer: str, amount: float) -> dict:
        """
        Simulate creating a Xero invoice for a customer.

        Args:
            customer: Customer / contact name.
            amount:   Invoice total (positive float, in USD by default).

        Returns:
            dict with invoice_id, customer, amount, status, and timestamp.
        """
        global _invoice_counter
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            if not customer or not str(customer).strip():
                raise ValueError("customer must be a non-empty string")
            if not isinstance(amount, (int, float)) or amount <= 0:
                raise ValueError("amount must be a positive number")

            _invoice_counter += 1
            invoice_id = f"INV-{_invoice_counter:03d}"

            result = {
                "invoice_id": invoice_id,
                "customer":   str(customer).strip(),
                "amount":     round(float(amount), 2),
                "status":     "created",
                "timestamp":  timestamp,
            }

            self._write_accounting_log(result)
            log_action(
                SERVER_NAME,
                "create_invoice",
                {
                    "invoice_id": invoice_id,
                    "customer":   result["customer"],
                    "amount":     result["amount"],
                },
            )
            return result

        except Exception as exc:
            error_result = {
                "invoice_id": None,
                "customer":   str(customer),
                "amount":     amount,
                "status":     "error",
                "timestamp":  timestamp,
                "error":      str(exc),
            }
            log_action(
                SERVER_NAME,
                "create_invoice_error",
                {"customer": str(customer), "amount": amount, "error": str(exc)},
                success=False,
            )
            return error_result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_accounting_log(self, entry: dict) -> None:
        """Append entry to /Logs/accounting.json (JSON array on disk)."""
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            existing: list = []
            if ACCOUNTING_LOG.exists():
                try:
                    existing = json.loads(ACCOUNTING_LOG.read_text(encoding="utf-8"))
                    if not isinstance(existing, list):
                        existing = []
                except Exception:
                    existing = []
            existing.append(entry)
            ACCOUNTING_LOG.write_text(
                json.dumps(existing, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass  # never crash on log write failure


if __name__ == "__main__":
    tool = AccountingXeroTool()
    out = tool.create_invoice("Acme Corp", 1500.00)
    print(json.dumps(out, indent=2))
    out2 = tool.create_invoice("Beta Ltd", 299.99)
    print(json.dumps(out2, indent=2))
