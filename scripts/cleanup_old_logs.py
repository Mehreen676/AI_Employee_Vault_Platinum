"""
AI Employee Vault – Platinum Tier
Audit Log 90-Day Retention Policy

Module:   scripts/cleanup_old_logs.py
Version:  1.0.0

Responsibility:
    Enforces a 90-day rolling retention window on all vault log files.
    Any file in vault/Logs/ whose modification time is older than 90 days
    is deleted. JSONL aggregate logs (execution_log.json, health_log.json,
    rate_limit_state.json) are filtered in-place — only lines older than
    90 days are removed; the file itself is preserved.

    Separate vault directories scanned:
        vault/Logs/           — JSONL aggregate logs + per-day snapshot files
        vault/Retry_Queue/    — failed task records (same 90-day rule)
        vault/Deferred/email/ — deferred poll records (same 90-day rule)
        vault/Done/           — completed manifests (optional, --include-done flag)

    Safety rules:
        - DRY_RUN=true prints files that WOULD be deleted without deleting.
        - No file is deleted unless it is strictly older than --days (default 90).
        - Aggregated JSONL files are never fully deleted — only aged-out lines.
        - Deletion is logged to stdout with file path and age in days.
        - A summary is printed at the end: N files deleted, N lines purged.

CLI Usage (from project root):
    python scripts/cleanup_old_logs.py
    python scripts/cleanup_old_logs.py --days 30
    python scripts/cleanup_old_logs.py --dry-run
    python scripts/cleanup_old_logs.py --include-done
    python scripts/cleanup_old_logs.py --help
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_VAULT_ROOT   = _PROJECT_ROOT / "vault"
_LOGS_DIR     = _VAULT_ROOT / "Logs"
_RETRY_QUEUE  = _VAULT_ROOT / "Retry_Queue"
_DEFERRED_DIR = _VAULT_ROOT / "Deferred" / "email"
_DONE_DIR     = _VAULT_ROOT / "Done"

# JSONL aggregate files: lines are filtered by timestamp field; files not deleted wholesale.
_JSONL_AGGREGATES = {
    "execution_log.json",
    "health_log.json",
}

_TIMESTAMP_FIELDS = ("timestamp", "failed_at", "approved_at", "created_at")


def _parse_timestamp(record: dict) -> float | None:
    """
    Extract a UTC epoch from a log record by probing known timestamp fields.

    Returns None if no parseable timestamp is found.
    """
    for field in _TIMESTAMP_FIELDS:
        raw = record.get(field)
        if not raw:
            continue
        raw = str(raw).strip().rstrip("Z")
        # Try ISO 8601 with microseconds, then without.
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except ValueError:
                pass
    return None


def _age_days(mtime_epoch: float, now: float) -> float:
    return (now - mtime_epoch) / 86_400


def _filter_jsonl_inplace(
    path: Path,
    cutoff_epoch: float,
    dry_run: bool,
) -> int:
    """
    Remove lines from a JSONL file whose timestamp is older than *cutoff_epoch*.

    Returns the number of lines removed.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    kept: list[str] = []
    removed = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue

        ts = _parse_timestamp(record)
        if ts is not None and ts < cutoff_epoch:
            removed += 1
            if dry_run:
                age = _age_days(ts, cutoff_epoch + cutoff_epoch)  # approximate
                print(f"  [DRY_RUN] Would purge JSONL line (age ~{age:.0f}d): {line[:80]}...")
        else:
            kept.append(line)

    if removed > 0 and not dry_run:
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        if path.exists():
            path.unlink()
        tmp.rename(path)

    return removed


def _delete_old_file(
    path: Path,
    cutoff_epoch: float,
    now: float,
    dry_run: bool,
) -> bool:
    """
    Delete *path* if its mtime is older than *cutoff_epoch*.

    Returns True if the file was deleted (or would be in dry-run).
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False

    age = _age_days(mtime, now)
    if mtime < cutoff_epoch:
        if dry_run:
            print(f"  [DRY_RUN] Would delete ({age:.1f}d old): {path}")
        else:
            try:
                path.unlink()
                print(f"  [DELETED]  ({age:.1f}d old): {path}")
            except OSError as exc:
                print(f"  [ERROR]    Could not delete {path}: {exc}", file=sys.stderr)
                return False
        return True
    return False


def run_cleanup(days: int, dry_run: bool, include_done: bool) -> None:
    """
    Main cleanup routine.

    Args:
        days:         Retention period in days.
        dry_run:      If True, print actions but make no changes.
        include_done: If True, also clean up vault/Done/ manifests.
    """
    now           = time.time()
    cutoff_epoch  = now - (days * 86_400)
    cutoff_label  = datetime.fromtimestamp(cutoff_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print()
    print("=" * 64)
    print("  AI Employee Vault – Platinum Tier")
    print("  Audit Log 90-Day Retention Cleanup v1.0.0")
    print("=" * 64)
    print(f"  Retention : {days} days")
    print(f"  Cutoff    : {cutoff_label}")
    print(f"  DRY_RUN   : {'YES — no changes will be made' if dry_run else 'NO — files will be deleted'}")
    print("=" * 64)
    print()

    files_deleted  = 0
    lines_purged   = 0

    # --- 1. Logs directory ---
    if _LOGS_DIR.exists():
        for f in sorted(_LOGS_DIR.glob("*")):
            if not f.is_file():
                continue
            if f.name in _JSONL_AGGREGATES:
                # Filter in-place — do not delete the whole file.
                removed = _filter_jsonl_inplace(f, cutoff_epoch, dry_run)
                if removed:
                    lines_purged += removed
                    if not dry_run:
                        print(f"  [PURGED]   {removed} aged lines from: {f.name}")
            else:
                # Plain files: delete if old enough.
                if _delete_old_file(f, cutoff_epoch, now, dry_run):
                    files_deleted += 1

    # --- 2. Retry_Queue ---
    if _RETRY_QUEUE.exists():
        for f in sorted(_RETRY_QUEUE.glob("*.json")):
            if _delete_old_file(f, cutoff_epoch, now, dry_run):
                files_deleted += 1

    # --- 3. Deferred/email ---
    if _DEFERRED_DIR.exists():
        for f in sorted(_DEFERRED_DIR.glob("*.json")):
            if _delete_old_file(f, cutoff_epoch, now, dry_run):
                files_deleted += 1

    # --- 4. Done/ (optional) ---
    if include_done and _DONE_DIR.exists():
        for f in sorted(_DONE_DIR.glob("*.json")):
            if _delete_old_file(f, cutoff_epoch, now, dry_run):
                files_deleted += 1

    # --- Summary ---
    print()
    print("=" * 64)
    if dry_run:
        print(f"  [DRY_RUN] Would delete : {files_deleted} file(s)")
        print(f"  [DRY_RUN] Would purge  : {lines_purged} JSONL line(s)")
    else:
        print(f"  Deleted  : {files_deleted} file(s)")
        print(f"  Purged   : {lines_purged} JSONL line(s)")
    print("=" * 64)
    print()


def main() -> None:
    # Also honour DRY_RUN env var.
    env_dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    parser = argparse.ArgumentParser(
        prog="cleanup_old_logs",
        description=(
            "AI Employee Vault – Platinum Tier: Audit Log 90-Day Retention.\n"
            "Deletes vault log files and purges JSONL lines older than --days.\n"
            "Set DRY_RUN=true or pass --dry-run to preview without deleting."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        metavar="N",
        help="Retention window in days (default: 90).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=env_dry_run,
        help="Print actions without making any changes (also set via DRY_RUN=true).",
    )
    parser.add_argument(
        "--include-done",
        action="store_true",
        help="Also clean up vault/Done/ task manifests older than --days.",
    )

    args = parser.parse_args()
    run_cleanup(days=args.days, dry_run=args.dry_run, include_done=args.include_done)


if __name__ == "__main__":
    main()
