"""
odoo_client.py — Odoo 19 Community JSON-RPC client (Gold Tier).

Connects to any Odoo 14–19 instance via the standard /jsonrpc endpoint.
No external dependencies — stdlib only (urllib + json).

Functions
---------
    OdooClient.from_env()           Build client from env vars (see below).
    client.ping()                   Return Odoo server version dict.
    client.authenticate()           Authenticate; returns uid (int).
    client.execute(model, method)   Raw execute_kw call on any model.
    client.create_partner_stub()    Create a res.partner record.
    client.create_invoice_stub()    Create an account.move (out_invoice).
    client.list_invoices()          search_read invoices with optional filter.

    test_connection()               Quick end-to-end connectivity check.

Environment variables (set in .env — see .env.example)
-------------------------------------------------------
    ODOO_URL        Base URL, e.g. http://localhost:8069
                    (no trailing slash; http:// for local dev)
    ODOO_DB         Database name shown in Settings -> General -> Database
    ODOO_USERNAME   Login username / email address
                    (ODOO_USER is also accepted for backward compatibility)
    ODOO_PASSWORD   User password OR Odoo API key
                    (Settings -> Activate developer mode ->
                     Technical -> API Keys -> New)
    ODOO_TIMEOUT_S  Network timeout in seconds (default: 30)

Security
--------
Never commit .env — it is in .gitignore.
Use Odoo API keys (instead of plain passwords) where possible;
API keys can be scoped and revoked without changing your login.

See docs/ODOO_SETUP.md for the full step-by-step guide.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any


# ── Custom exception ──────────────────────────────────────────────────────────

class OdooError(Exception):
    """Raised on JSON-RPC errors, auth failures, or missing configuration."""


# ── Client ────────────────────────────────────────────────────────────────────

class OdooClient:
    """
    Thin wrapper around the Odoo JSON-RPC /jsonrpc endpoint.

    Instantiate via OdooClient.from_env() to read credentials from .env.
    All network calls use stdlib urllib — no third-party dependencies.
    """

    def __init__(
        self,
        url: str,
        db: str,
        user: str,
        password: str,
        timeout: int = 30,
    ) -> None:
        self._url      = url.rstrip("/")
        self._db       = db
        self._user     = user
        self._password = password
        self._timeout  = timeout
        self._uid: int | None = None
        self._rpc_id   = 0

    # ── Constructor helpers ───────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "OdooClient":
        """
        Build an OdooClient from environment variables.

        Reads (in priority order):
            ODOO_URL       — required
            ODOO_DB        — required
            ODOO_USERNAME  — required (ODOO_USER accepted as fallback)
            ODOO_PASSWORD  — required
            ODOO_TIMEOUT_S — optional, default 30

        Raises OdooError if any required var is missing.
        """
        url      = os.getenv("ODOO_URL",      "").strip().rstrip("/")
        db       = os.getenv("ODOO_DB",       "").strip()
        # Support both ODOO_USERNAME (preferred) and ODOO_USER (legacy)
        user     = (
            os.getenv("ODOO_USERNAME", "").strip()
            or os.getenv("ODOO_USER",     "").strip()
        )
        password = os.getenv("ODOO_PASSWORD", "").strip()
        timeout  = int(os.getenv("ODOO_TIMEOUT_S", "30"))

        missing = [
            name
            for name, val in [
                ("ODOO_URL",      url),
                ("ODOO_DB",       db),
                ("ODOO_USERNAME", user),
                ("ODOO_PASSWORD", password),
            ]
            if not val
        ]
        if missing:
            raise OdooError(
                f"Missing required Odoo env vars: {', '.join(missing)}.\n"
                "Set them in .env (copy from .env.example).\n"
                "See docs/ODOO_SETUP.md for instructions."
            )

        return cls(url, db, user, password, timeout)

    # ── Raw JSON-RPC transport ────────────────────────────────────────────────

    def _call(self, service: str, method: str, *args: Any) -> Any:
        """
        Execute one JSON-RPC 2.0 call against  <ODOO_URL>/jsonrpc.

        Args:
            service:  "common" | "object" | "report"
            method:   e.g. "authenticate", "execute_kw", "version"
            *args:    positional args forwarded in params.args

        Returns:
            The JSON-RPC result value (already unwrapped from the envelope).

        Raises:
            OdooError on HTTP errors, JSON-RPC error responses, or timeouts.
        """
        self._rpc_id += 1
        body = json.dumps({
            "jsonrpc": "2.0",
            "method":  "call",
            "id":       self._rpc_id,
            "params": {
                "service": service,
                "method":  method,
                "args":    list(args),
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url     = f"{self._url}/jsonrpc",
            data    = body,
            headers = {"Content-Type": "application/json"},
            method  = "POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                response = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OdooError(
                f"HTTP {exc.code} from {self._url}/jsonrpc — {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OdooError(
                f"Cannot reach Odoo at {self._url}: {exc.reason}\n"
                "Check ODOO_URL in .env and ensure the server is running."
            ) from exc
        except Exception as exc:
            raise OdooError(f"JSON-RPC transport error: {exc}") from exc

        if "error" in response:
            err  = response["error"]
            data = err.get("data", {}) or {}
            msg  = data.get("message") or err.get("message") or str(err)
            raise OdooError(
                f"Odoo JSON-RPC error [{err.get('code', '?')}]: {msg}"
            )

        return response.get("result")

    # ── Authentication ────────────────────────────────────────────────────────

    def ping(self) -> dict:
        """
        Call common/version — does NOT require authentication.
        Returns a dict with keys: server_version, server_serie, protocol_version.
        Useful as a quick connectivity check.
        """
        result = self._call("common", "version")
        return result if isinstance(result, dict) else {}

    def authenticate(self) -> int:
        """
        Authenticate with ODOO_USERNAME / ODOO_PASSWORD.

        Returns the user's uid (int > 0) and caches it for subsequent calls.
        Raises OdooError if credentials are invalid.
        """
        uid = self._call(
            "common", "authenticate",
            self._db, self._user, self._password, {}
        )
        if not uid:
            raise OdooError(
                f"Authentication failed for user {self._user!r} "
                f"on database {self._db!r}.\n"
                "Check ODOO_USERNAME and ODOO_PASSWORD in .env.\n"
                "See docs/ODOO_SETUP.md — Troubleshooting."
            )
        self._uid = int(uid)
        return self._uid

    def _ensure_auth(self) -> int:
        """Lazy authenticate. Returns cached uid without a new network call."""
        if self._uid is None:
            self.authenticate()
        return self._uid  # type: ignore[return-value]

    # ── Model execute_kw ─────────────────────────────────────────────────────

    def execute(
        self,
        model:  str,
        method: str,
        args:   list  | None = None,
        kwargs: dict  | None = None,
    ) -> Any:
        """
        Call execute_kw on any Odoo model.

        Equivalent to:
            models.execute_kw(db, uid, password, model, method, args, kwargs)

        Args:
            model:   e.g. "res.partner", "account.move"
            method:  e.g. "create", "write", "search_read", "unlink"
            args:    positional args list (default [])
            kwargs:  keyword args dict   (default {})
        """
        uid = self._ensure_auth()
        return self._call(
            "object", "execute_kw",
            self._db, uid, self._password,
            model, method,
            args   or [],
            kwargs or {},
        )

    # ── High-level helpers ────────────────────────────────────────────────────

    def create_partner_stub(
        self,
        name:    str,
        email:   str = "",
        phone:   str = "",
        company: str = "",
        **extra_vals: Any,
    ) -> int:
        """
        Create a res.partner record and return its ID.

        Args:
            name:     Contact full name (required)
            email:    Email address
            phone:    Phone number
            company:  Company name (sets company_name field)
            **extra_vals: Any other valid res.partner field values

        Returns:
            int — the new partner's database ID
        """
        vals: dict[str, Any] = {"name": name}
        if email:
            vals["email"] = email
        if phone:
            vals["phone"] = phone
        if company:
            vals["company_name"] = company
        vals.update(extra_vals)

        partner_id = self.execute("res.partner", "create", [vals])
        return int(partner_id)

    def create_invoice_stub(
        self,
        partner_id:    int,
        lines:         list[dict] | None = None,
        currency_code: str = "USD",
        ref:           str = "",
    ) -> int:
        """
        Create a customer invoice (account.move, move_type='out_invoice').

        Args:
            partner_id:    res.partner ID to bill
            lines:         List of invoice line dicts, each with:
                               name        (str)   — product/service description
                               quantity    (float) — quantity (default 1.0)
                               price_unit  (float) — unit price
            currency_code: ISO 4217 currency code (default "USD")
            ref:           Optional vendor/customer reference string

        Returns:
            int — the new invoice's database ID

        Note:
            To post (confirm) the invoice after creation call:
                client.execute("account.move", "action_post", [[invoice_id]])
        """
        line_commands: list = []
        for line in (lines or [{"name": "Service", "quantity": 1.0, "price_unit": 0.0}]):
            line_commands.append((0, 0, {
                "name":       str(line.get("name", "Service")),
                "quantity":   float(line.get("quantity", 1.0)),
                "price_unit": float(line.get("price_unit", 0.0)),
            }))

        vals: dict[str, Any] = {
            "move_type":        "out_invoice",
            "partner_id":       partner_id,
            "invoice_line_ids": line_commands,
        }
        if ref:
            vals["ref"] = ref

        invoice_id = self.execute("account.move", "create", [vals])
        return int(invoice_id)

    def list_invoices(
        self,
        limit:      int            = 20,
        state:      str | None     = None,
        move_types: list[str] | None = None,
    ) -> list[dict]:
        """
        search_read account.move (invoices).

        Args:
            limit:      Maximum records to return (default 20)
            state:      Filter by invoice state: "draft" | "posted" | "cancel"
            move_types: List of move_type values to include
                        (default: ["out_invoice", "in_invoice"])

        Returns:
            List of dicts with keys:
                id, name, partner_id, amount_total, state,
                invoice_date, move_type
        """
        types  = move_types or ["out_invoice", "in_invoice"]
        domain: list = [["move_type", "in", types]]

        if state:
            domain.append(["state", "=", state])

        return self.execute(
            "account.move",
            "search_read",
            [domain],
            {
                "fields": [
                    "id", "name", "partner_id",
                    "amount_total", "state",
                    "invoice_date", "move_type",
                ],
                "limit": max(1, int(limit)),
                "order": "invoice_date desc, id desc",
            },
        )


# ── Module-level convenience ──────────────────────────────────────────────────

def test_connection() -> dict:
    """
    Quick end-to-end connectivity + auth check.

    Reads credentials from env vars. Calls ping() then authenticate().
    Returns:
        {
          "ok":      bool,
          "version": dict (Odoo server version info),
          "uid":     int  (authenticated user ID),
          "url":     str,
          "db":      str,
          "user":    str,
        }
    Raises OdooError on any failure.

    Usage:
        python -c "from odoo_client import test_connection; print(test_connection())"
    """
    client  = OdooClient.from_env()
    version = client.ping()
    uid     = client.authenticate()
    return {
        "ok":      True,
        "version": version,
        "uid":     uid,
        "url":     client._url,
        "db":      client._db,
        "user":    client._user,
    }


if __name__ == "__main__":
    import sys
    print("Testing Odoo connection …")
    try:
        info = test_connection()
        print(f"  [OK]  Connected to {info['url']}")
        print(f"      DB:      {info['db']}")
        print(f"      User:    {info['user']}  (uid={info['uid']})")
        sv = info.get("version", {})
        print(f"      Odoo:    {sv.get('server_version', '?')}")
    except OdooError as exc:
        print(f"  [FAIL]  {exc}")
        sys.exit(1)
