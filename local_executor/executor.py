"""
AI Employee Vault – Platinum Tier
Local Executor — Core Implementation

Module:   local_executor/executor.py
Version:  1.2.0

Responsibility:
    Watches vault/Pending_Approval/ for task manifest files.
    For each manifest found:
        1. Reads and parses the JSON manifest.
        2. Guards against replay within the current session.
        3. Logs task_execution_started via PromptLogger.
        4. Mutates manifest: status → "approved", records timestamp.
        5. Atomically moves manifest to vault/Done/ (write-tmp → rename).
        6. If task_type == "odoo": calls odoo_client.py to create partner
           and draft invoice; logs result as "success" or "error: <reason>".
        7. Appends a structured record to vault/Logs/execution_log.json.
        8. Logs task_completed via PromptLogger.
        9. Prints a confirmation line to stdout.

    NOTE: In this phase the executor auto-approves tasks from Pending_Approval/
    directly. In Phase 3, a human approval UI will be inserted between
    Pending_Approval/ and Approved/ before this executor picks up the task.

CLI Usage (from project root):
    python -m local_executor.executor --poll 2
    python -m local_executor.executor --once
    python -m local_executor.executor --once --vault /path/to/vault

Spec Reference:
    specs/architecture.md § 4.2
    specs/distributed_flow.md § Phase 3
    specs/security_model.md § 3.1
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys as _sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Bootstrap prompt_logger via direct file load.
# The project's logging/ directory shares its name with Python's stdlib
# logging module. importlib.util loads it by path, sidestepping the collision.
# The module is registered in sys.modules before exec_module so that
# @dataclass can resolve cls.__module__ without raising AttributeError.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent

_pl_spec = importlib.util.spec_from_file_location(
    "prompt_logger",
    _PROJECT_ROOT / "logging" / "prompt_logger.py",
)
_pl_mod = importlib.util.module_from_spec(_pl_spec)
_sys.modules.setdefault("prompt_logger", _pl_mod)
_pl_spec.loader.exec_module(_pl_mod)

PromptLogger = _pl_mod.PromptLogger
EventType    = _pl_mod.EventType
Component    = _pl_mod.Component

# ---------------------------------------------------------------------------
# Vault paths
# ---------------------------------------------------------------------------

_VAULT_ROOT = _PROJECT_ROOT / "vault"

# ---------------------------------------------------------------------------
# Dotenv loader (stdlib only — no python-dotenv dependency).
# Loads .env from project root into os.environ before Odoo client reads vars.
# Only sets keys that are not already present in the environment.
# ---------------------------------------------------------------------------


def _load_dotenv(env_path: Path) -> None:
    """Load key=value pairs from *env_path* into os.environ if file exists."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key   = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# Odoo task runner
# Loaded lazily via importlib.util to avoid hard import dependency.
# Gracefully degrades when odoo_client.py is absent or env vars are unset.
# ---------------------------------------------------------------------------

_ODOO_CONTENT_RE = re.compile(
    r"Create partner:\s*(.+?),\s*Create draft invoice:\s*([\d.]+)\s*AED",
    re.IGNORECASE,
)


def _run_odoo_task(content: str) -> str:
    """
    Execute an approved odoo task: create a partner and a draft AED invoice.

    Steps:
        1. Load .env (if present) into os.environ.
        2. Import odoo_client.py by file path.
        3. Build OdooClient.from_env() — raises OdooError if vars missing.
        4. Parse partner name and amount from task content.
        5. Authenticate, create partner, create draft invoice.
        6. Return "success: partner_id=<id> invoice_id=<id>"
           or   "error: <reason>" on any failure.

    Failure modes:
        - odoo_client.py not found          → "error: odoo_client.py not found"
        - Env vars missing / unconfigured   → "error: odoo tool not configured"
        - Content format unrecognised       → "error: cannot parse content"
        - Network / auth / API failure      → "error: <exception message>"
    """
    _load_dotenv(_PROJECT_ROOT / ".env")

    odoo_path = _PROJECT_ROOT / "odoo_client.py"
    if not odoo_path.exists():
        return "error: odoo_client.py not found"

    # Load odoo_client module by path to avoid import system collisions.
    try:
        _oc_spec = importlib.util.spec_from_file_location("odoo_client", odoo_path)
        _oc_mod  = importlib.util.module_from_spec(_oc_spec)
        _sys.modules.setdefault("odoo_client", _oc_mod)
        _oc_spec.loader.exec_module(_oc_mod)
        OdooClient = _oc_mod.OdooClient
    except Exception as exc:
        return f"error: failed to load odoo_client: {exc}"

    # Attempt to build client from env vars — fails fast if unconfigured.
    try:
        client = OdooClient.from_env()
    except Exception:
        return "error: odoo tool not configured"

    # Parse content: "Create partner: <name>, Create draft invoice: <amount> AED"
    match = _ODOO_CONTENT_RE.match(content.strip())
    if not match:
        return f"error: cannot parse odoo content: {content[:80]}"

    partner_name = match.group(1).strip()
    amount       = float(match.group(2))

    try:
        client.authenticate()
        partner_id  = client.create_partner_stub(name=partner_name)
        invoice_id  = client.create_invoice_stub(
            partner_id=partner_id,
            lines=[{"name": "Service", "quantity": 1.0, "price_unit": amount}],
            currency_code="AED",
        )
        return f"success: partner_id={partner_id} invoice_id={invoice_id}"
    except Exception as exc:
        return f"error: {str(exc)[:200]}"


# ---------------------------------------------------------------------------
# LocalExecutor
# ---------------------------------------------------------------------------


class LocalExecutor:
    """
    Watches vault/Pending_Approval/ and processes task manifests.

    Polling-based watcher: scans the directory every `poll_interval` seconds.
    All file transitions use atomic rename — no partially-written files
    are ever observable by other components.

    Every action is recorded through PromptLogger and appended to
    history/prompt_log.json.

    Args:
        vault_path:     Optional override for the vault root directory.
                        Defaults to <project_root>/vault.
        poll_interval:  Seconds between Pending_Approval/ scans. Default: 2.
        executor_id:    Identity string for this executor instance.
                        Auto-generated UUID if not provided.
    """

    def __init__(
        self,
        vault_path: Optional[Path] = None,
        poll_interval: float = 2.0,
        executor_id: Optional[str] = None,
    ) -> None:
        vault_root = Path(vault_path) if vault_path else _VAULT_ROOT

        self._pending       = vault_root / "Pending_Approval"
        self._done          = vault_root / "Done"
        self._logs          = vault_root / "Logs"
        self._execution_log = self._logs / "execution_log.json"

        self._poll_interval = poll_interval
        self._executor_id   = executor_id or str(uuid.uuid4())
        self._processed: set[str] = set()   # task_id dedup within session

        # Ensure vault output directories exist.
        self._pending.mkdir(parents=True, exist_ok=True)
        self._done.mkdir(parents=True, exist_ok=True)
        self._logs.mkdir(parents=True, exist_ok=True)

        self._logger = PromptLogger(
            component=Component.LOCAL_EXECUTOR,
            executor_version="1.2.0",
        )

        self._logger.log(
            event_type=EventType.SYSTEM_STARTUP,
            summary="Local Executor initialised",
            detail=(
                f"Executor ID: {self._executor_id} | "
                f"Watching: {self._pending} | "
                f"Poll interval: {self._poll_interval}s"
            ),
            metadata_extra={"executor_id": self._executor_id},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def watch(self) -> None:
        """
        Begin the watch loop. Blocks indefinitely until CTRL+C.

        Scans vault/Pending_Approval/ every poll_interval seconds and
        processes every .json manifest file found.
        """
        _print_banner(self._executor_id, self._pending, self._poll_interval,
                      self._execution_log)

        try:
            while True:
                self._scan()
                time.sleep(self._poll_interval)
        except KeyboardInterrupt:
            print()
            print("[LocalExecutor] Interrupted by user. Shutting down.")
            self._logger.log(
                event_type=EventType.SYSTEM_SHUTDOWN,
                summary="Local Executor shutdown via KeyboardInterrupt",
                detail="User pressed CTRL+C.",
            )

    def process_once(self) -> int:
        """
        Run a single scan of Pending_Approval/ and process all found files.

        Returns:
            Number of task files processed in this scan.
        """
        return self._scan()

    # ------------------------------------------------------------------
    # Internal scan + process
    # ------------------------------------------------------------------

    def _scan(self) -> int:
        """Scan Pending_Approval/ and process every .json manifest present."""
        manifest_files = sorted(self._pending.glob("*.json"))
        if not manifest_files:
            return 0

        processed_count = 0
        for manifest_path in manifest_files:
            try:
                self._process(manifest_path)
                processed_count += 1
            except Exception as exc:
                self._logger.log(
                    event_type=EventType.TASK_FAILED,
                    summary=f"Error processing {manifest_path.name}",
                    detail=str(exc),
                )
                print(f"[LocalExecutor] ERROR  {manifest_path.name}: {exc}")

        return processed_count

    def _process(self, manifest_path: Path) -> None:
        """
        Process a single task manifest from vault/Pending_Approval/.

        Steps:
            1. Read and parse manifest JSON.
            2. Replay guard — skip if task_id was already processed this session.
            3. Log task_execution_started.
            4. Mutate manifest: status -> "approved", record timestamp.
            5. Write updated manifest to vault/Done/ via tmp-then-rename.
            6. Delete original from vault/Pending_Approval/.
            7. Append entry to vault/Logs/execution_log.json.
            8. Log task_completed.
            9. Print confirmation to stdout.
        """
        # --- 1. Read manifest ---
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self._logger.log(
                event_type=EventType.TASK_VALIDATION_FAILED,
                summary=f"Cannot read/parse manifest: {manifest_path.name}",
                detail=str(exc),
            )
            return

        task_id:   str = manifest.get("id", "unknown")
        task_type: str = manifest.get("task_type", "unknown")

        # --- 2. Replay guard ---
        if task_id in self._processed:
            self._logger.log_security_event(
                event_type=EventType.SECURITY_REPLAY_DETECTED,
                summary="Replay detected — task already processed this session",
                detail=f"task_id: {task_id} | file: {manifest_path.name}",
                task_id=task_id,
            )
            return

        # --- 3. Log start ---
        self._logger.log(
            event_type=EventType.TASK_EXECUTION_STARTED,
            summary=f"Processing task [{task_type}] from Pending_Approval/",
            detail=f"File: {manifest_path.name} | Task ID: {task_id}",
            task_id=task_id,
            metadata_extra={"executor_id": self._executor_id},
        )

        # --- 4. Mutate manifest ---
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        manifest["status"]       = "approved"
        manifest["approved_at"]  = now_iso
        manifest["processed_by"] = self._executor_id

        # --- 5 & 6. Atomic move to Done/ ---
        filename   = manifest_path.name
        tmp_path   = self._done / (filename + ".tmp")
        dest_path  = self._done / filename

        tmp_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Delete source first (required on Windows before rename over an
        # existing path), then promote tmp to final destination.
        manifest_path.unlink()
        tmp_path.rename(dest_path)

        # --- 7. Run integration handler (odoo tasks only) ---
        if task_type == "odoo":
            content = manifest.get("content", "")
            odoo_result = _run_odoo_task(content)
            self._logger.log(
                event_type=EventType.TASK_COMPLETED,
                summary=f"Odoo task execution: {odoo_result[:80]}",
                detail=f"task_id={task_id} | content={content[:120]} | result={odoo_result}",
                task_id=task_id,
                metadata_extra={"odoo_result": odoo_result, "executor_id": self._executor_id},
            )
        else:
            odoo_result = "success"

        # --- 8. Append to execution_log.json ---
        self._append_execution_log(
            task_id=task_id,
            task_type=task_type,
            timestamp=now_iso,
            result=odoo_result,
        )

        # --- 9. Log completion ---
        self._logger.log(
            event_type=EventType.TASK_COMPLETED,
            summary=f"Task approved and moved to Done/: [{task_type}]",
            detail=f"File: {filename} | result={odoo_result}",
            task_id=task_id,
            metadata_extra={
                "executor_id": self._executor_id,
                "dest_file": filename,
                "from": "Pending_Approval",
                "to": "Done",
                "result": odoo_result,
            },
        )

        # --- 10. Mark processed and confirm ---
        self._processed.add(task_id)
        _print_task_line(task_type, task_id, filename, odoo_result)

    # ------------------------------------------------------------------
    # Execution log writer
    # ------------------------------------------------------------------

    def _append_execution_log(
        self,
        task_id: str,
        task_type: str,
        timestamp: str,
        result: str = "success",
    ) -> None:
        """
        Append one JSON record to vault/Logs/execution_log.json.

        File is JSONL — one object per line. Append-only; never re-opened
        for overwrite. fsync guarantees the write survives a process crash.

        Record format:
            {
                "id":        "<task uuid>",
                "task_type": "<string>",
                "action":    "approved_and_moved",
                "timestamp": "<ISO-8601 UTC>",
                "from":      "Pending_Approval",
                "to":        "Done",
                "result":    "success" | "error: <reason>"
            }
        """
        record = {
            "id":        task_id,
            "task_type": task_type,
            "action":    "approved_and_moved",
            "timestamp": timestamp,
            "from":      "Pending_Approval",
            "to":        "Done",
            "result":    result,
        }
        with self._execution_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------


def _print_banner(
    executor_id: str,
    pending: Path,
    poll_interval: float,
    execution_log: Path,
) -> None:
    print()
    print("=" * 64)
    print("  AI Employee Vault - Platinum Tier")
    print("  Local Executor - Active")
    print("=" * 64)
    print(f"  Executor ID  : {executor_id[:16]}...")
    print(f"  Watching     : {pending}")
    print(f"  Poll interval: {poll_interval}s")
    print(f"  Done dir     : {pending.parent / 'Done'}")
    print(f"  Exec log     : {execution_log}")
    print("=" * 64)
    print("  Waiting for tasks... (CTRL+C to stop)")
    print()


def _print_task_line(task_type: str, task_id: str, filename: str, result: str = "success") -> None:
    ts     = datetime.now(timezone.utc).strftime("%H:%M:%S")
    status = "OK" if result == "success" or result.startswith("success") else "ERR"
    print(
        f"  [DONE] {ts}  type={task_type:<24}  "
        f"id={task_id[:8]}...  -> Done/{filename}  [{status}]"
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="local_executor.executor",
        description=(
            "AI Employee Vault - Platinum Tier: Local Executor.\n"
            "Watches vault/Pending_Approval/ and processes task manifests."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Seconds between directory scans (default: 2).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scan and exit instead of looping.",
    )
    parser.add_argument(
        "--vault",
        type=str,
        default=None,
        metavar="PATH",
        help="Override path to the vault root directory.",
    )

    args = parser.parse_args()

    vault_path = Path(args.vault) if args.vault else None
    executor   = LocalExecutor(vault_path=vault_path, poll_interval=args.poll)

    if args.once:
        count = executor.process_once()
        print(f"[LocalExecutor] Single scan complete. Tasks processed: {count}")
    else:
        executor.watch()
