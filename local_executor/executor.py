"""
AI Employee Vault – Platinum Tier
Local Executor — Core Implementation

Module:   local_executor/executor.py
Version:  1.3.0

Changes in v1.3.0:
    - Claim-by-move: tasks are now atomically renamed from vault/Pending_Approval/
      to vault/In_Progress/local/ before processing. This prevents two executor
      instances from picking up the same file (distributed lock via filesystem).
      Execution log records now include a "via" field showing the intermediate
      directory.
    - Single-writer Dashboard.md: _write_dashboard() is called after each scan
      batch. Cloud Agent status is read from vault/Updates/cloud_updates.md and
      merged. No other component may write Dashboard.md.
    - New vault directories managed: In_Progress/local/ (created on init).

Responsibility:
    Watches vault/Pending_Approval/ for task manifest files.
    For each manifest found:
        1. Reads and parses the JSON manifest.
        2. Guards against replay within the current session.
        3. Logs task_execution_started via PromptLogger.
        4. Atomically claims: renames manifest from Pending_Approval/ to
           In_Progress/local/ (distributed lock — first rename wins).
        5. Mutates manifest: status -> "approved", records timestamp.
        6. If task_type == "odoo": calls odoo_client.py to create partner
           and draft invoice; logs result as "success" or "error: <reason>".
        7. Atomically moves manifest from In_Progress/local/ to Done/.
        8. Appends a structured record to vault/Logs/execution_log.json.
        9. Logs task_completed via PromptLogger.
       10. Writes Dashboard.md (single-writer rule).
       11. Prints a confirmation line to stdout.

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

# Ensure project root is on sys.path so utils.* imports resolve.
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# DRY_RUN — global env flag.
# When DRY_RUN=true the executor validates manifests and logs actions but does
# NOT move any files between vault directories. External integrations (Odoo)
# are also skipped. Safe for CI, staging, and end-to-end integration tests.
# ---------------------------------------------------------------------------
_DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"

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

from utils.retry import with_retry          # noqa: E402
from utils.rate_limiter import get_limiter  # noqa: E402

# ---------------------------------------------------------------------------
# Vault paths
# ---------------------------------------------------------------------------

_VAULT_ROOT   = _PROJECT_ROOT / "vault"
_RETRY_QUEUE  = _VAULT_ROOT / "Retry_Queue"  # failed non-payment tasks pending retry

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


@with_retry(max_attempts=3, base_delay=5.0, backoff=2.0, jitter=True,
            exceptions=(Exception,))
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
        - odoo_client.py not found          -> "error: odoo_client.py not found"
        - Env vars missing / unconfigured   -> "error: odoo tool not configured"
        - Content format unrecognised       -> "error: cannot parse content"
        - Network / auth / API failure      -> "error: <exception message>"
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

    Claim-by-move (v1.3.0): each manifest is atomically renamed from
    Pending_Approval/ to In_Progress/local/ before any processing begins.
    The first executor to rename the file owns it. Other instances skip it.

    Single-writer rule (v1.3.0): Dashboard.md is written exclusively by
    LocalExecutor._write_dashboard(). Cloud Agent status is sourced from
    vault/Updates/cloud_updates.md and merged in.

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

        self._vault_root        = vault_root
        self._pending           = vault_root / "Pending_Approval"
        self._in_progress_local = vault_root / "In_Progress" / "local"
        self._done              = vault_root / "Done"
        self._logs              = vault_root / "Logs"
        self._execution_log     = self._logs / "execution_log.json"
        self._cloud_updates     = vault_root / "Updates" / "cloud_updates.md"
        self._dashboard         = _PROJECT_ROOT / "Dashboard.md"

        self._poll_interval = poll_interval
        self._executor_id   = executor_id or str(uuid.uuid4())
        self._processed: set[str] = set()   # task_id dedup within session

        # Ensure vault output directories exist.
        for _dir in [
            self._pending,
            self._in_progress_local,
            self._done,
            self._logs,
            _RETRY_QUEUE,
        ]:
            _dir.mkdir(parents=True, exist_ok=True)

        self._rate   = get_limiter()
        self._logger = PromptLogger(
            component=Component.LOCAL_EXECUTOR,
            executor_version="1.3.0",
        )

        self._logger.log(
            event_type=EventType.SYSTEM_STARTUP,
            summary="Local Executor initialised (v1.3.0)",
            detail=(
                f"Executor ID: {self._executor_id} | "
                f"Watching: {self._pending} | "
                f"In_Progress/local: {self._in_progress_local} | "
                f"Poll interval: {self._poll_interval}s | "
                f"DRY_RUN: {_DRY_RUN}"
            ),
            metadata_extra={"executor_id": self._executor_id},
        )
        if _DRY_RUN:
            print("  [LocalExecutor] DRY_RUN=true — vault file moves will NOT be executed.")
            self._logger.log(
                event_type=EventType.SYSTEM_STARTUP,
                summary="DRY_RUN mode active — no files will be moved",
                detail="Set DRY_RUN=false to enable real task processing.",
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

        if processed_count > 0:
            self._write_dashboard()

        return processed_count

    def _process(self, manifest_path: Path) -> None:
        """
        Process a single task manifest from vault/Pending_Approval/.

        Steps:
            1.  Read and parse manifest JSON.
            2.  Replay guard — skip if task_id was already processed this session.
            3.  Log task_execution_started.
            4.  Claim: atomic rename Pending_Approval/<file> -> In_Progress/local/<file>.
                If rename fails (another executor claimed it), skip silently.
            5.  Mutate manifest: status -> "approved", record timestamp.
            6.  Run integration handler (odoo tasks only).
            7.  Write updated manifest to Done/ via tmp-then-rename.
            8.  Unlink file from In_Progress/local/.
            9.  Append entry to vault/Logs/execution_log.json.
            10. Log task_completed.
            11. Print confirmation to stdout.
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

        # --- 3. Rate limit check ---
        # Map task_type to a rate-limit category.
        _rate_category = (
            "payment" if task_type == "odoo"
            else "email" if task_type == "email"
            else "file"
        )
        _allowed, _reason = self._rate.check(_rate_category)
        if not _allowed:
            self._logger.log(
                event_type=EventType.TASK_FAILED,
                summary=f"Rate limit reached for [{_rate_category}] — skipping task",
                detail=_reason,
                task_id=task_id,
            )
            print(f"  [LocalExecutor] RATE LIMIT [{_rate_category}]: {_reason}")
            return

        # --- 4. DRY_RUN shortcut ---
        if _DRY_RUN:
            self._logger.log(
                event_type=EventType.TASK_COMPLETED,
                summary=f"[DRY_RUN] Would process [{task_type}] — skipped",
                detail=f"File: {manifest_path.name} | task_id={task_id}",
                task_id=task_id,
                metadata_extra={"dry_run": True, "executor_id": self._executor_id},
            )
            print(f"  [DRY_RUN] Would move: {manifest_path.name} -> Done/")
            self._processed.add(task_id)
            return

        # --- 5. Log start ---
        self._logger.log(
            event_type=EventType.TASK_EXECUTION_STARTED,
            summary=f"Processing task [{task_type}] from Pending_Approval/",
            detail=f"File: {manifest_path.name} | Task ID: {task_id}",
            task_id=task_id,
            metadata_extra={"executor_id": self._executor_id},
        )

        # --- 6. Claim by atomic rename: Pending_Approval/ -> In_Progress/local/ ---
        filename         = manifest_path.name
        in_progress_path = self._in_progress_local / filename

        try:
            manifest_path.rename(in_progress_path)
        except (OSError, FileExistsError):
            # Another executor claimed it first — skip silently.
            self._logger.log(
                event_type=EventType.TASK_FAILED,
                summary=f"Claim failed (race) — skipping: {filename}",
                detail=f"Rename {manifest_path} -> {in_progress_path} failed.",
                task_id=task_id,
            )
            return

        # --- 7. Mutate manifest ---
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        manifest["status"]       = "approved"
        manifest["approved_at"]  = now_iso
        manifest["processed_by"] = self._executor_id

        # --- 8. Run integration handler (odoo tasks only) ---
        # Odoo calls have @with_retry (3 attempts, exponential backoff).
        # On failure, route to vault/Retry_Queue/ — NEVER auto-retry payments.
        if task_type == "odoo":
            content = manifest.get("content", "")
            try:
                odoo_result = _run_odoo_task(content)
            except Exception as exc:
                odoo_result = f"error: {str(exc)[:200]}"

            if odoo_result.startswith("error"):
                # Write to Retry_Queue/ for human review.
                # Payments are marked no_auto_retry=True in rate_limiter limits.
                self._write_retry_queue(task_id, task_type, content, odoo_result, now_iso)

            self._logger.log(
                event_type=EventType.TASK_COMPLETED,
                summary=f"Odoo task execution: {odoo_result[:80]}",
                detail=f"task_id={task_id} | content={content[:120]} | result={odoo_result}",
                task_id=task_id,
                metadata_extra={"odoo_result": odoo_result, "executor_id": self._executor_id},
            )
        else:
            odoo_result = "success"

        # Record rate limit increment after successful task pickup.
        self._rate.record(_rate_category)

        # --- 7. Write updated manifest to Done/ via tmp-then-rename ---
        tmp_path  = self._done / (filename + ".tmp")
        dest_path = self._done / filename

        tmp_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # --- 8. Unlink In_Progress/local/ copy, promote tmp to Done/ ---
        in_progress_path.unlink()
        tmp_path.rename(dest_path)

        # --- 9. Append to execution_log.json ---
        self._append_execution_log(
            task_id=task_id,
            task_type=task_type,
            timestamp=now_iso,
            result=odoo_result,
        )

        # --- 10. Log completion ---
        self._logger.log(
            event_type=EventType.TASK_COMPLETED,
            summary=f"Task approved and moved to Done/: [{task_type}]",
            detail=f"File: {filename} | via=In_Progress/local | result={odoo_result}",
            task_id=task_id,
            metadata_extra={
                "executor_id": self._executor_id,
                "dest_file":   filename,
                "from":        "Pending_Approval",
                "via":         "In_Progress/local",
                "to":          "Done",
                "result":      odoo_result,
            },
        )

        # --- 11. Mark processed and confirm ---
        self._processed.add(task_id)
        _print_task_line(task_type, task_id, filename, odoo_result)

    # ------------------------------------------------------------------
    # Retry Queue writer (graceful degradation)
    # ------------------------------------------------------------------

    def _write_retry_queue(
        self,
        task_id: str,
        task_type: str,
        content: str,
        error: str,
        timestamp: str,
    ) -> None:
        """
        Write a failed task to vault/Retry_Queue/ for human review.

        Called when an Odoo task exhausts all @with_retry attempts.

        Graceful degradation rules:
            - Payment tasks (task_type="odoo") must NEVER be auto-retried.
              The record is written to Retry_Queue/ and flagged no_auto_retry=True.
            - A human must inspect and re-queue manually.
            - All failures are logged via PromptLogger.

        File naming:
            retry_<task_id_short>_<timestamp_slug>.json
        """
        no_auto_retry = task_type in ("odoo", "payment")
        ts_slug = timestamp.replace(":", "").replace(".", "").replace("Z", "")[:17]
        filename = f"retry_{task_id[:8]}_{ts_slug}.json"
        dest = _RETRY_QUEUE / filename

        record = {
            "task_id":       task_id,
            "task_type":     task_type,
            "content":       content,
            "error":         error,
            "failed_at":     timestamp,
            "no_auto_retry": no_auto_retry,
            "reviewed":      False,
        }

        tmp = _RETRY_QUEUE / (filename + ".tmp")
        try:
            tmp.write_text(
                json.dumps(record, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            if dest.exists():
                dest.unlink()
            tmp.rename(dest)
        except OSError as exc:
            self._logger.log(
                event_type=EventType.TASK_FAILED,
                summary=f"Failed to write Retry_Queue entry: {filename}",
                detail=str(exc),
                task_id=task_id,
            )
            return

        no_retry_note = " — PAYMENT: no auto-retry, human review required" if no_auto_retry else ""
        self._logger.log(
            event_type=EventType.TASK_FAILED,
            summary=f"Task routed to Retry_Queue/{filename}{no_retry_note}",
            detail=f"task_id={task_id} | error={error[:120]} | no_auto_retry={no_auto_retry}",
            task_id=task_id,
            metadata_extra={"retry_queue_file": str(dest), "no_auto_retry": no_auto_retry},
        )
        print(
            f"  [RETRY_QUEUE] {task_type} task {task_id[:8]}... -> "
            f"vault/Retry_Queue/{filename}{no_retry_note}"
        )

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

        Record format (v1.3.0):
            {
                "id":        "<task uuid>",
                "task_type": "<string>",
                "action":    "approved_and_moved",
                "timestamp": "<ISO-8601 UTC>",
                "from":      "Pending_Approval",
                "via":       "In_Progress/local",
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
            "via":       "In_Progress/local",
            "to":        "Done",
            "result":    result,
        }
        with self._execution_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    # ------------------------------------------------------------------
    # Dashboard writer (single-writer rule)
    # ------------------------------------------------------------------

    def _write_dashboard(self) -> None:
        """
        Write Dashboard.md to the project root.

        Single-writer rule: ONLY LocalExecutor._write_dashboard() may write
        this file. Cloud Agent status is sourced from vault/Updates/cloud_updates.md
        and merged here — the Cloud Agent never touches Dashboard.md directly.

        Dashboard sections:
            - Header with last-updated timestamp and executor ID
            - Vault state table (counts per directory)
            - Recent Executions (last 5 from execution_log.json)
            - Cloud Agent Updates (last 20 lines from cloud_updates.md)
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # --- Count vault state ---
        pending_count = len(list(self._pending.glob("*.json")))
        done_count    = len(list(self._done.glob("*.json")))
        in_prog_local = len(list(self._in_progress_local.glob("*.json")))

        in_prog_cloud_dir = self._vault_root / "In_Progress" / "cloud"
        in_prog_cloud = (
            len(list(in_prog_cloud_dir.glob("*")))
            if in_prog_cloud_dir.exists() else 0
        )
        needs_action_dir = self._vault_root / "Needs_Action"
        needs_action = (
            len([f for f in needs_action_dir.rglob("*") if f.is_file()])
            if needs_action_dir.exists() else 0
        )

        # --- Read last 5 execution log entries ---
        exec_entries: list[dict] = []
        if self._execution_log.exists():
            lines = self._execution_log.read_text(encoding="utf-8").strip().splitlines()
            for line in lines[-5:]:
                try:
                    exec_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        # --- Compose dashboard ---
        lines_out = [
            "# AI Employee Vault - Dashboard",
            "",
            f"**Last updated:** {now}",
            f"**Writer:** Local Executor `{self._executor_id[:16]}...` (single-writer rule enforced)",
            f"**Version:** executor v1.3.0",
            "",
            "---",
            "",
            "## Vault State",
            "",
            "| Directory | File Count |",
            "|---|---|",
            f"| `vault/Needs_Action/` | {needs_action} |",
            f"| `vault/In_Progress/cloud/` | {in_prog_cloud} |",
            f"| `vault/In_Progress/local/` | {in_prog_local} |",
            f"| `vault/Pending_Approval/` | {pending_count} |",
            f"| `vault/Done/` | {done_count} |",
            "",
            "---",
            "",
            "## Recent Executions",
            "",
        ]

        if exec_entries:
            for entry in exec_entries:
                ts      = entry.get("timestamp", "?")[:19] + "Z"
                tt      = entry.get("task_type", "?")
                tid     = entry.get("id", "?")[:8]
                result  = entry.get("result", "?")
                lines_out.append(
                    f"- `{ts}`  [{tt}]  id={tid}...  result={result}"
                )
        else:
            lines_out.append("_No executions recorded yet._")

        # --- Merge Cloud Agent updates ---
        if self._cloud_updates.exists():
            cloud_content = self._cloud_updates.read_text(encoding="utf-8").strip()
            last_lines = "\n".join(cloud_content.splitlines()[-20:])
            lines_out += [
                "",
                "---",
                "",
                "## Cloud Agent Updates",
                "",
                last_lines,
                "",
            ]

        self._dashboard.write_text(
            "\n".join(lines_out) + "\n",
            encoding="utf-8",
        )


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
    print("  Local Executor v1.3.0 - Active")
    print("=" * 64)
    print(f"  Executor ID  : {executor_id[:16]}...")
    print(f"  Watching     : {pending}")
    print(f"  Claim into   : {pending.parent / 'In_Progress' / 'local'}")
    print(f"  Poll interval: {poll_interval}s")
    print(f"  Done dir     : {pending.parent / 'Done'}")
    print(f"  Exec log     : {execution_log}")
    print(f"  Dashboard    : Dashboard.md (single-writer)")
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
            "AI Employee Vault - Platinum Tier: Local Executor v1.3.0.\n"
            "Watches vault/Pending_Approval/ and processes task manifests.\n"
            "Claims via In_Progress/local/. Writes Dashboard.md (single-writer)."
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
