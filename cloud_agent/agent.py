"""
AI Employee Vault – Platinum Tier
Cloud Agent — Core Implementation

Module:   cloud_agent/agent.py
Version:  1.3.0

Responsibility:
    Accepts task specifications and writes structured task manifests to
    vault/Pending_Approval/ using atomic file operations.

    Supports three operating modes:
        Single-shot   — Submit one task programmatically via submit_task().
        Auto mode     — Continuously generate tasks at a fixed interval.
                        Activated by the --auto CLI flag.
        Daemon mode   — Always-on 24/7 worker. Emits a heartbeat log every
                        interval. Optionally generates tasks if --auto is
                        also supplied. Activated by the --daemon CLI flag.

    Work Zones: tasks are routed into one of five named zones:
        email | calendar | docs | finance | social

    Special task types (enqueued for human approval; NOT executed by Cloud Agent):
        odoo  — Creates a partner + draft invoice in Odoo via Local Executor.
                Zone: finance. Content: "Create partner: <name>, Create draft invoice: <amount> AED"

    Queue discipline: filenames are UUID-based; a collision check with
    retry guarantees the Cloud Agent never overwrites an existing task.

    All activity is recorded through the Platinum prompt logging subsystem
    and appended to history/prompt_log.json.

CLI Usage (from project root):
    python cloud_agent.py --auto
    python cloud_agent.py --auto --interval 10 --task-type email
    python cloud_agent.py --daemon
    python cloud_agent.py --daemon --auto --interval 5
    python cloud_agent.py --daemon --auto --interval 5 --task-type finance

Spec Reference:
    specs/architecture.md § 4.1
    specs/platinum_design.md § 3.1, § 4
    specs/distributed_flow.md § Phase 1
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
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

_VAULT_ROOT    = _PROJECT_ROOT / "vault"
_VAULT_PENDING = _VAULT_ROOT / "Pending_Approval"

# ---------------------------------------------------------------------------
# Work Zones — five named routing zones with realistic task content.
# The task_type field in every manifest is set to the zone name.
# CLI --task-type selects a zone; omitting it picks one at random.
# ---------------------------------------------------------------------------

_ZONES: list[str] = ["email", "calendar", "docs", "finance", "social"]

_ZONE_CATALOGUE: dict[str, list[str]] = {
    "email": [
        "Draft a follow-up email to Acme Corp regarding the Q1 pilot proposal agreed on 2026-02-20.",
        "Compose a meeting request to the board for the March 2026 strategy review.",
        "Write an internal announcement for the updated expense-claim policy effective 2026-04-01.",
        "Reply to the vendor RFP from DataStream Ltd requesting a 10-day extension.",
    ],
    "calendar": [
        "Schedule the Q2 planning session for the week of 2026-03-09 with all department heads.",
        "Block 3 hours of focus time on 2026-03-04 for contract review — no interruptions.",
        "Add a recurring stand-up at 09:00 UTC Mon-Fri for the platform engineering team.",
        "Move the client demo originally set for 2026-03-01 to 2026-03-03 at 14:00 UTC.",
    ],
    "docs": [
        "Create a project brief for the new customer onboarding workflow redesign.",
        "Update the API reference documentation to reflect v2.1 endpoint changes released 2026-02-25.",
        "Draft the Q1 retrospective document including wins, misses, and action items.",
        "Write a one-page executive summary of the Platinum Tier architecture for the CTO.",
    ],
    "finance": [
        "Reconcile March 2026 expense claims against approved departmental budgets and flag variances.",
        "Generate a cash flow forecast for Q2 2026 based on current signed-contract pipeline data.",
        "Flag all invoices overdue by more than 30 days and route to accounts receivable for follow-up.",
        "Prepare a budget variance report comparing Q1 actuals versus Q1 forecast by cost centre.",
    ],
    "social": [
        "Draft a LinkedIn post announcing the Platinum Tier product launch targeted at enterprise buyers.",
        "Schedule three X (Twitter) posts for the upcoming AI Summit conference on 2026-03-15.",
        "Write a short company update for the internal Slack #announcements channel — 150 words max.",
        "Compose an Instagram caption for the team photo from the February 2026 all-hands event.",
    ],
    # Special task type: zone=finance, task_type=odoo.
    # Enqueued as pending — executed by Local Executor via odoo_client.py.
    # Content pattern: "Create partner: <name>, Create draft invoice: <amount> AED"
    "odoo": [
        "Create partner: Acme Trading LLC, Create draft invoice: 5000 AED",
        "Create partner: Gulf Supplies Co, Create draft invoice: 12500 AED",
        "Create partner: Delta Logistics FZE, Create draft invoice: 8750 AED",
        "Create partner: Al Futtaim Enterprises, Create draft invoice: 22000 AED",
        "Create partner: Horizon Consulting DMCC, Create draft invoice: 3400 AED",
    ],
}


# ---------------------------------------------------------------------------
# CloudAgent
# ---------------------------------------------------------------------------


class CloudAgent:
    """
    Cognitive core of the Platinum Tier system.

    Generates task manifests from task specifications and writes them
    atomically to vault/Pending_Approval/. Every action is logged through
    PromptLogger and appended to history/prompt_log.json.

    This class does NOT execute tasks. Execution is the exclusive domain
    of local_executor.executor.LocalExecutor.

    Args:
        vault_path: Optional override for the vault root directory.
                    Defaults to <project_root>/vault.
    """

    def __init__(self, vault_path: Optional[Path] = None) -> None:
        vault_root = Path(vault_path) if vault_path else _VAULT_ROOT

        # Ensure vault directories exist before anything else.
        self._pending = vault_root / "Pending_Approval"
        self._pending.mkdir(parents=True, exist_ok=True)

        self._logger = PromptLogger(component=Component.CLOUD_AGENT)

        self._logger.log(
            event_type=EventType.SYSTEM_STARTUP,
            summary="Cloud Agent initialised",
            detail=f"Vault Pending_Approval: {self._pending}",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pick_task(self, task_type: Optional[str]) -> tuple[str, str, str]:
        """
        Select a (zone, content, effective_task_type) triple for one task submission.

        Special handling:
            task_type == "odoo"  → zone="finance", task_type="odoo", Odoo AED content.
            task_type in _ZONES  → zone=task_type, task_type=zone, zone catalogue content.
            task_type is None    → random zone, task_type=zone, zone catalogue content.

        Returns:
            (zone, content, effective_task_type) — all strings.
        """
        if task_type == "odoo":
            return "finance", random.choice(_ZONE_CATALOGUE["odoo"]), "odoo"
        zone = task_type if task_type in _ZONES else random.choice(_ZONES)
        content = random.choice(_ZONE_CATALOGUE[zone])
        return zone, content, zone

    def _unique_task_path(self) -> tuple[str, Path]:
        """
        Return (task_id, final_path) guaranteed not to exist.

        Generates a new UUID until the target filename is absent from
        vault/Pending_Approval/, providing lightweight write-lock semantics.
        """
        for _ in range(10):
            task_id    = str(uuid.uuid4())
            final_path = self._pending / f"task_{task_id}.json"
            if not final_path.exists():
                return task_id, final_path
        # Extremely unlikely; last resort
        task_id    = str(uuid.uuid4())
        return task_id, self._pending / f"task_{task_id}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_task(
        self,
        task_type: str,
        content: str,
        zone: Optional[str] = None,
    ) -> str:
        """
        Create one task manifest and write it to vault/Pending_Approval/.

        Manifest schema (Platinum Tier v1.2):
            {
                "id":         "<uuid-v4>",
                "task_type":  "<zone name>",
                "zone":       "<zone name>",
                "content":    "<string>",
                "created_at": "<ISO-8601 UTC>",
                "status":     "pending"
            }

        The file is written via write-to-tmp then atomic rename so the
        Local Executor never observes a partially-written manifest.
        A collision check ensures no existing task file is overwritten.

        File name: task_<uuid>.json

        Args:
            task_type:  Zone / categorical task type string.
            content:    Human-readable task instruction.
            zone:       Explicit zone override. Defaults to task_type.

        Returns:
            The UUID string assigned to this task.
        """
        task_id, final_path = self._unique_task_path()
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        effective_zone = zone or task_type

        manifest = {
            "id":         task_id,
            "task_type":  task_type,
            "zone":       effective_zone,
            "content":    content,
            "created_at": created_at,
            "status":     "pending",
        }

        filename = final_path.name
        tmp_path = self._pending / (filename + ".tmp")

        tmp_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Atomic: manifest appears in the directory only after this rename.
        tmp_path.rename(final_path)

        self._logger.log(
            event_type=EventType.TASK_SUBMITTED,
            summary=f"Task submitted to Vault: [{task_type}] zone={effective_zone}",
            detail=(
                f"File: {filename} | "
                f"Content preview: {content[:120]}"
            ),
            task_id=task_id,
            metadata_extra={
                "vault_file": filename,
                "task_type":  task_type,
                "zone":       effective_zone,
            },
        )

        return task_id

    def auto_run(
        self,
        interval: float = 10.0,
        task_type: Optional[str] = None,
    ) -> None:
        """
        Continuously generate tasks at a fixed interval (no heartbeat).

        Each cycle picks a zone (random or pinned via task_type) and submits
        one task. Blocks until CTRL+C.

        Args:
            interval:  Seconds between submissions. Default: 10.
            task_type: Zone to pin. If None, picks randomly each cycle.
        """
        _print_banner("auto", interval, task_type)

        task_count = 0

        self._logger.log(
            event_type=EventType.SYSTEM_STARTUP,
            summary="Cloud Agent auto mode started",
            detail=(
                f"Interval: {interval}s | "
                f"Zone filter: {task_type or 'random'} | "
                f"Zones available: {len(_ZONES)}"
            ),
            metadata_extra={"mode": "auto", "interval_seconds": interval, "zone_filter": task_type},
        )

        try:
            while True:
                zone, content, tt = self._pick_task(task_type)
                task_id = self.submit_task(
                    task_type=tt,
                    content=content,
                    zone=zone,
                )
                task_count += 1
                _print_task_line(task_count, tt, task_id)
                time.sleep(interval)

        except KeyboardInterrupt:
            print()
            print("[CloudAgent] Auto mode interrupted. Shutting down.")
            self.shutdown(
                detail=f"Auto mode stopped after {task_count} task(s) submitted."
            )

    def daemon_run(
        self,
        interval: float = 10.0,
        auto: bool = False,
        task_type: Optional[str] = None,
    ) -> None:
        """
        Always-on daemon mode (24/7 style).

        Every cycle:
            1. Emits a HEALTH_CHECK heartbeat log entry with UTC timestamp.
            2. If auto=True, also submits one task (zone-routed).

        Blocks until CTRL+C.

        Args:
            interval:  Seconds between cycles. Default: 10.
            auto:      If True, generate a task each cycle in addition to heartbeat.
            task_type: Zone to pin for task generation. If None, picks randomly.
        """
        _print_banner("daemon", interval, task_type, auto=auto)

        cycle_count = 0
        task_count  = 0

        self._logger.log(
            event_type=EventType.SYSTEM_STARTUP,
            summary="Cloud Agent daemon started",
            detail=(
                f"Interval: {interval}s | "
                f"auto={auto} | "
                f"Zone filter: {task_type or 'random'}"
            ),
            metadata_extra={
                "mode": "daemon",
                "interval_seconds": interval,
                "auto": auto,
                "zone_filter": task_type,
            },
        )

        try:
            while True:
                cycle_count += 1
                now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

                # --- Heartbeat ---
                self._logger.log(
                    event_type=EventType.HEALTH_CHECK,
                    summary=f"Daemon heartbeat #{cycle_count}",
                    detail=f"timestamp={now} | auto={auto} | interval={interval}s",
                    metadata_extra={
                        "cycle":     cycle_count,
                        "timestamp": now,
                        "auto":      auto,
                    },
                )
                _print_heartbeat(cycle_count, now)

                # --- Optional task generation ---
                if auto:
                    zone, content, tt = self._pick_task(task_type)
                    task_id = self.submit_task(
                        task_type=tt,
                        content=content,
                        zone=zone,
                    )
                    task_count += 1
                    _print_task_line(task_count, tt, task_id)

                time.sleep(interval)

        except KeyboardInterrupt:
            print()
            print("[CloudAgent] Daemon interrupted. Shutting down.")
            self.shutdown(
                detail=(
                    f"Daemon stopped after {cycle_count} cycle(s), "
                    f"{task_count} task(s) submitted."
                )
            )

    def list_pending(self) -> list[dict]:
        """
        Return all task manifests currently in vault/Pending_Approval/.

        Returns:
            List of manifest dicts, sorted by filename.
        """
        manifests = []
        for path in sorted(self._pending.glob("task_*.json")):
            try:
                manifests.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        return manifests

    def shutdown(self, detail: str = "Shutdown requested by caller.") -> None:
        """Log a clean shutdown event."""
        self._logger.log(
            event_type=EventType.SYSTEM_SHUTDOWN,
            summary="Cloud Agent shutting down",
            detail=detail,
        )


# ---------------------------------------------------------------------------
# Console helpers (ASCII-safe — no Unicode box-drawing characters)
# ---------------------------------------------------------------------------


def _print_banner(
    mode: str,
    interval: float,
    task_type: Optional[str],
    auto: bool = False,
) -> None:
    zone_label = task_type if task_type else "random"
    print()
    print("=" * 66)
    print("  AI Employee Vault - Platinum Tier")
    print(f"  Cloud Agent - {'Daemon (always-on)' if mode == 'daemon' else 'Auto Task Generator'}")
    print("=" * 66)
    print(f"  Mode         : {mode}")
    if mode == "daemon":
        print(f"  Task gen     : {'enabled (--auto)' if auto else 'disabled'}")
    print(f"  Interval     : {interval}s")
    print(f"  Zone filter  : {zone_label}")
    print(f"  Zones        : {', '.join(_ZONES)}")
    print(f"  Destination  : vault/Pending_Approval/task_<uuid>.json")
    print(f"  Logging      : history/prompt_log.json")
    print("=" * 66)
    print("  Press CTRL+C to stop.")
    print()


def _print_heartbeat(cycle: int, timestamp: str) -> None:
    print(f"  [HB #{cycle:04d}] {timestamp}  heartbeat")


def _print_task_line(count: int, zone: str, task_id: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"  [TASK {count:04d}] {ts}  zone={zone:<12}  id={task_id[:8]}...")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="cloud_agent.agent",
        description=(
            "AI Employee Vault - Platinum Tier: Cloud Agent.\n"
            "Generates task manifests in vault/Pending_Approval/.\n\n"
            "Modes:\n"
            "  --auto            continuous task generation\n"
            "  --daemon          always-on heartbeat loop\n"
            "  --daemon --auto   heartbeat + task generation combined\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--auto",
        action="store_true",
        help="Generate tasks continuously (each interval).",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in always-on daemon mode with heartbeat logging.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="Seconds between cycles (default: 10).",
    )
    _ALL_TASK_TYPES = _ZONES + ["odoo"]
    parser.add_argument(
        "--task-type",
        type=str,
        default=None,
        choices=_ALL_TASK_TYPES,
        metavar="TYPE",
        help=(
            f"Pin task type: {{{', '.join(_ALL_TASK_TYPES)}}}. "
            "'odoo' enqueues partner+invoice tasks (zone=finance). "
            "Picks randomly from zones if omitted."
        ),
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
    agent      = CloudAgent(vault_path=vault_path)

    if args.daemon:
        agent.daemon_run(
            interval=args.interval,
            auto=args.auto,
            task_type=args.task_type,
        )
    elif args.auto:
        agent.auto_run(
            interval=args.interval,
            task_type=args.task_type,
        )
    else:
        parser.print_help()
        print()
        print("Hint: use --auto, --daemon, or --daemon --auto to start.")
        agent.shutdown()
        _sys.exit(0)
