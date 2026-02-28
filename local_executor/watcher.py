"""
AI Employee Vault – Platinum Tier
Local Executor — Watcher Entrypoint

Module:   local_executor/watcher.py
Version:  1.0.0

Description:
    CLI entrypoint for the Local Executor watch loop.
    Starts a blocking poll of vault/Pending_Approval/ and processes
    every task manifest that appears.

Usage (from project root):
    python -m local_executor.watcher
    python -m local_executor.watcher --poll 5
    python -m local_executor.watcher --once

    --poll SECONDS    Poll interval in seconds (default: 3)
    --once            Run one scan and exit (non-blocking, for testing)

Spec Reference:
    specs/platinum_design.md § 3.3
    specs/distributed_flow.md § Phase 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from .executor import LocalExecutor
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from local_executor.executor import LocalExecutor  # type: ignore[no-redef]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="local_executor.watcher",
        description="Watch vault/Pending_Approval/ and process task manifests.",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Poll interval in seconds (default: 2).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan and exit instead of looping.",
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
    executor = LocalExecutor(vault_path=vault_path, poll_interval=args.poll)

    if args.once:
        count = executor.process_once()
        print(f"[watcher] Single scan complete. Tasks processed: {count}")
    else:
        executor.watch()


if __name__ == "__main__":
    main()
