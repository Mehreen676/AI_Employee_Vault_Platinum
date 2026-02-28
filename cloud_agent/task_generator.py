"""
AI Employee Vault – Platinum Tier
Cloud Agent — Example Task Generator

Module:   cloud_agent/task_generator.py
Version:  1.0.0

Description:
    Seeds vault/Pending_Approval/ with a set of realistic example tasks.
    Demonstrates the Cloud Agent's task submission workflow end-to-end.

    This is NOT a mock. It creates real task manifest files that the
    Local Executor will detect and process.

Usage (from project root):
    python -m cloud_agent.task_generator
    python -m cloud_agent.task_generator --count 1
    python -m cloud_agent.task_generator --task-type code_review

Spec Reference:
    specs/distributed_flow.md § Phase 1 (Steps 1.1 – 1.4)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Intra-package import. Works both when run as `python -m cloud_agent.task_generator`
# (package context) and when the project root is in sys.path.
# ---------------------------------------------------------------------------

try:
    from .agent import CloudAgent
except ImportError:
    # Fallback for direct script execution: inject project root into path.
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from cloud_agent.agent import CloudAgent  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Example task catalogue
# ---------------------------------------------------------------------------

EXAMPLE_TASKS: list[dict] = [
    {
        "task_type": "summarize_document",
        "content": (
            "Summarize the Q1 2026 sales performance report. "
            "Extract: total revenue, top 3 product categories, "
            "regional breakdown, and YoY growth percentage."
        ),
        "priority": 5,
    },
    {
        "task_type": "code_review",
        "content": (
            "Review the authentication module (auth/jwt_handler.py) "
            "for security vulnerabilities. Focus on: token expiry enforcement, "
            "signature validation, and privilege escalation vectors."
        ),
        "priority": 8,
    },
    {
        "task_type": "data_analysis",
        "content": (
            "Analyse customer churn data for March 2026. "
            "Identify the top 3 churn drivers, segment by subscription tier, "
            "and produce a risk-ranked cohort list."
        ),
        "priority": 6,
    },
    {
        "task_type": "draft_email",
        "content": (
            "Draft a professional follow-up email to the enterprise sales lead "
            "at Acme Corp. Reference the demo on 2026-02-20 and propose "
            "next steps for a 90-day pilot agreement."
        ),
        "priority": 4,
    },
    {
        "task_type": "research",
        "content": (
            "Research competitor pricing models for AI workflow automation tools "
            "in the SME market segment. Summarise into a comparison table: "
            "pricing tiers, feature set, and deployment model."
        ),
        "priority": 3,
    },
]


# ---------------------------------------------------------------------------
# Generator logic
# ---------------------------------------------------------------------------


def generate_tasks(count: int | None = None, task_type: str | None = None) -> None:
    """
    Submit example tasks to the Cloud Agent.

    Args:
        count:      Maximum number of tasks to submit. None = all.
        task_type:  If given, filter catalogue to this task_type only.
    """
    agent = CloudAgent()

    catalogue = EXAMPLE_TASKS
    if task_type:
        catalogue = [t for t in catalogue if t["task_type"] == task_type]
        if not catalogue:
            print(f"[task_generator] No tasks found for task_type='{task_type}'.")
            print(
                f"[task_generator] Available types: "
                + ", ".join(t["task_type"] for t in EXAMPLE_TASKS)
            )
            agent.shutdown()
            return

    if count is not None:
        catalogue = catalogue[:count]

    print()
    print("=" * 64)
    print(" AI Employee Vault – Platinum Tier")
    print(" Cloud Agent — Example Task Generator")
    print("=" * 64)
    print(f" Submitting {len(catalogue)} task(s) to vault/Pending_Approval/")
    print("=" * 64)

    for i, task in enumerate(catalogue, start=1):
        task_id = agent.submit_task(
            task_type=task["task_type"],
            content=task["content"],
        )
        print(
            f" [{i:02d}] type={task['task_type']:<22} "
            f"id={task_id[:8]}..."
        )

    print("=" * 64)
    print(f" Done. Check vault/Pending_Approval/ for manifest files.")
    print(f" Run `python -m local_executor.watcher` to process them.")
    print("=" * 64)
    print()

    agent.shutdown()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate example tasks into vault/Pending_Approval/."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of tasks to generate (default: all).",
    )
    parser.add_argument(
        "--task-type",
        type=str,
        default=None,
        dest="task_type",
        help="Generate only tasks of this type.",
    )
    args = parser.parse_args()
    generate_tasks(count=args.count, task_type=args.task_type)
