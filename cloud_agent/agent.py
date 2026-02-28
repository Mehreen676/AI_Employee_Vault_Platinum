"""
AI Employee Vault – Platinum Tier
Cloud Agent — Core Implementation

Module:   cloud_agent/agent.py
Version:  1.1.0

Responsibility:
    Accepts task specifications and writes structured task manifests to
    vault/Pending_Approval/ using atomic file operations.

    Supports two operating modes:
        Single-shot   — Submit one task programmatically via submit_task().
        Auto mode     — Continuously generate tasks at a fixed interval,
                        cycling through the built-in task catalogue.
                        Activated by the --auto CLI flag.

    All activity is recorded through the Platinum prompt logging subsystem
    and appended to history/prompt_log.json.

CLI Usage (from project root):
    python -m cloud_agent.agent --auto
    python -m cloud_agent.agent --auto --interval 10

Spec Reference:
    specs/architecture.md § 4.1
    specs/platinum_design.md § 3.1, § 4
    specs/distributed_flow.md § Phase 1
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import os
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
# Built-in task catalogue — used by auto mode to cycle through realistic tasks
# ---------------------------------------------------------------------------

_AUTO_CATALOGUE: list[dict] = [
    {
        "task_type": "summarize_document",
        "content": (
            "Summarize the Q1 2026 sales performance report. "
            "Extract: total revenue, top 3 product categories, "
            "regional breakdown, and YoY growth percentage."
        ),
    },
    {
        "task_type": "code_review",
        "content": (
            "Review the authentication module (auth/jwt_handler.py) "
            "for security vulnerabilities. Focus on: token expiry enforcement, "
            "signature validation, and privilege escalation vectors."
        ),
    },
    {
        "task_type": "data_analysis",
        "content": (
            "Analyse customer churn data for March 2026. "
            "Identify the top 3 churn drivers, segment by subscription tier, "
            "and produce a risk-ranked cohort list."
        ),
    },
    {
        "task_type": "draft_email",
        "content": (
            "Draft a professional follow-up email to the enterprise sales lead "
            "at Acme Corp. Reference the demo on 2026-02-20 and propose "
            "next steps for a 90-day pilot agreement."
        ),
    },
    {
        "task_type": "research",
        "content": (
            "Research competitor pricing models for AI workflow automation tools "
            "in the SME market segment. Summarise into a comparison table: "
            "pricing tiers, feature set, and deployment model."
        ),
    },
    {
        "task_type": "generate_report",
        "content": (
            "Generate a weekly operational status report for the platform "
            "engineering team. Include: deployment count, incident count, "
            "mean time to recovery, and open critical issues."
        ),
    },
    {
        "task_type": "compliance_check",
        "content": (
            "Perform a GDPR compliance review on the user data export feature. "
            "Verify: consent capture, data minimisation, right-to-erasure path, "
            "and audit log completeness."
        ),
    },
    {
        "task_type": "sentiment_analysis",
        "content": (
            "Run sentiment analysis on February 2026 customer support tickets. "
            "Classify by: positive / neutral / negative, and identify "
            "the top 5 recurring complaint themes."
        ),
    },
]


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
    # Public API
    # ------------------------------------------------------------------

    def submit_task(self, task_type: str, content: str) -> str:
        """
        Create one task manifest and write it to vault/Pending_Approval/.

        Manifest conforms to the Platinum Tier schema:
            {
                "id":         "<uuid-v4>",
                "task_type":  "<string>",
                "content":    "<string>",
                "created_at": "<ISO-8601 UTC>",
                "status":     "pending"
            }

        The file is written via write-to-tmp then atomic rename so the
        Local Executor never observes a partially-written manifest.

        File name: task_<uuid>.json

        Args:
            task_type:  Categorical task type string.
            content:    Human-readable task instruction.

        Returns:
            The UUID string assigned to this task.
        """
        task_id     = str(uuid.uuid4())
        created_at  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

        manifest = {
            "id":         task_id,
            "task_type":  task_type,
            "content":    content,
            "created_at": created_at,
            "status":     "pending",
        }

        filename   = f"task_{task_id}.json"
        tmp_path   = self._pending / (filename + ".tmp")
        final_path = self._pending / filename

        tmp_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Atomic: manifest appears in the directory only after this rename.
        tmp_path.rename(final_path)

        self._logger.log(
            event_type=EventType.TASK_SUBMITTED,
            summary=f"Task submitted to Vault: [{task_type}]",
            detail=(
                f"File: {filename} | "
                f"Content preview: {content[:120]}"
            ),
            task_id=task_id,
            metadata_extra={
                "vault_file": filename,
                "task_type":  task_type,
            },
        )

        return task_id

    def auto_run(self, interval: float = 10.0) -> None:
        """
        Continuously generate tasks at a fixed interval.

        Cycles through the built-in _AUTO_CATALOGUE indefinitely using
        itertools.cycle so the sequence repeats without bound. Sleeps
        `interval` seconds between submissions.

        Blocks until interrupted by CTRL+C (KeyboardInterrupt).

        Args:
            interval: Seconds to wait between task submissions. Default: 10.
        """
        _print_banner(interval)

        catalogue_cycle = itertools.cycle(_AUTO_CATALOGUE)
        task_count      = 0

        self._logger.log(
            event_type=EventType.SYSTEM_STARTUP,
            summary="Cloud Agent auto mode started",
            detail=f"Interval: {interval}s | Catalogue size: {len(_AUTO_CATALOGUE)} tasks",
            metadata_extra={"mode": "auto", "interval_seconds": interval},
        )

        try:
            while True:
                entry   = next(catalogue_cycle)
                task_id = self.submit_task(
                    task_type=entry["task_type"],
                    content=entry["content"],
                )
                task_count += 1
                _print_task_line(task_count, entry["task_type"], task_id)

                time.sleep(interval)

        except KeyboardInterrupt:
            print()
            print("[CloudAgent] Auto mode interrupted. Shutting down.")
            self.shutdown(
                detail=f"Auto mode stopped after {task_count} task(s) submitted."
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


def _print_banner(interval: float) -> None:
    print()
    print("=" * 64)
    print("  AI Employee Vault - Platinum Tier")
    print("  Cloud Agent - Auto Task Generator")
    print("=" * 64)
    print(f"  Interval     : {interval}s between submissions")
    print(f"  Catalogue    : {len(_AUTO_CATALOGUE)} task types (cycling)")
    print(f"  Destination  : vault/Pending_Approval/task_<uuid>.json")
    print(f"  Logging      : history/prompt_log.json")
    print("=" * 64)
    print("  Press CTRL+C to stop.")
    print()


def _print_task_line(count: int, task_type: str, task_id: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(
        f"  [{count:04d}] {ts}  type={task_type:<24}  id={task_id[:8]}..."
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="cloud_agent.agent",
        description=(
            "AI Employee Vault - Platinum Tier: Cloud Agent.\n"
            "Generates task manifests in vault/Pending_Approval/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run in continuous auto-generation mode (CTRL+C to stop).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="Seconds between task submissions in auto mode (default: 10).",
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

    if args.auto:
        agent.auto_run(interval=args.interval)
    else:
        parser.print_help()
        print()
        print("Hint: use --auto to start continuous task generation.")
        agent.shutdown()
        _sys.exit(0)
