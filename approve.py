"""
AI Employee Vault - Platinum Tier
HITL Approval CLI

True HITL gate:
    vault/Waiting_Approval/ -> vault/Pending_Approval/ (approve)
    vault/Waiting_Approval/ -> vault/Rejected/         (reject)

Usage:
    python approve.py list
    python approve.py approve <task_file_or_id>
    python approve.py reject <task_file_or_id> [reason]
    python approve.py status
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VAULT_ROOT = PROJECT_ROOT / "vault"
WAITING_DIR = VAULT_ROOT / "Waiting_Approval"
PENDING_DIR = VAULT_ROOT / "Pending_Approval"
REJECTED_DIR = VAULT_ROOT / "Rejected"
DONE_DIR = VAULT_ROOT / "Done"
LOGS_DIR = VAULT_ROOT / "Logs"
APPROVAL_LOG = LOGS_DIR / "approval_log.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ensure_dirs() -> None:
    for path in (WAITING_DIR, PENDING_DIR, REJECTED_DIR, DONE_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _append_log(action: str, task_file: str, task_id: str, task_type: str, reason: str = "") -> None:
    record = {
        "timestamp": _utc_now(),
        "action": action,
        "task_file": task_file,
        "task_id": task_id,
        "task_type": task_type,
        "reason": reason,
    }
    with APPROVAL_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _read_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _list_waiting() -> list[Path]:
    return sorted(WAITING_DIR.glob("task_*.json"))


def _resolve_waiting_target(task_file_or_id: str) -> Path | None:
    direct = WAITING_DIR / task_file_or_id
    if direct.exists():
        return direct

    # Accept raw UUID -> task_<uuid>.json
    by_uuid = WAITING_DIR / f"task_{task_file_or_id}.json"
    if by_uuid.exists():
        return by_uuid

    # Accept short-id search against manifest id field
    needle = task_file_or_id.strip().lower()
    for path in _list_waiting():
        manifest = _read_manifest(path)
        task_id = str(manifest.get("id", "")).lower()
        if task_id.startswith(needle):
            return path
    return None


def cmd_list() -> int:
    waiting = _list_waiting()
    if not waiting:
        print("[approve] No tasks in vault/Waiting_Approval/.")
        return 0

    print(f"[approve] Waiting tasks: {len(waiting)}")
    for path in waiting:
        manifest = _read_manifest(path)
        task_id = str(manifest.get("id", "unknown"))
        task_type = str(manifest.get("task_type", "unknown"))
        created = str(manifest.get("created_at", "?"))
        print(f"  - {path.name}  id={task_id[:8]}...  type={task_type}  created={created}")
    return 0


def cmd_status() -> int:
    waiting = len(list(WAITING_DIR.glob("task_*.json")))
    pending = len(list(PENDING_DIR.glob("task_*.json")))
    done = len(list(DONE_DIR.glob("task_*.json")))
    rejected = len(list(REJECTED_DIR.glob("task_*.json")))

    print("[approve] Queue Status")
    print(f"  Waiting_Approval : {waiting}")
    print(f"  Pending_Approval : {pending}")
    print(f"  Done             : {done}")
    print(f"  Rejected         : {rejected}")
    return 0


def cmd_approve(task_file_or_id: str) -> int:
    src = _resolve_waiting_target(task_file_or_id)
    if src is None:
        print(f"[approve] Not found in Waiting_Approval: {task_file_or_id}")
        return 1

    dest = PENDING_DIR / src.name
    if dest.exists():
        print(f"[approve] Destination already exists: {dest.name}")
        return 1

    manifest = _read_manifest(src)
    task_id = str(manifest.get("id", "unknown"))
    task_type = str(manifest.get("task_type", "unknown"))

    try:
        src.rename(dest)  # atomic move on same filesystem
    except OSError as exc:
        print(f"[approve] Move failed: {exc}")
        return 1

    _append_log(
        action="approved_waiting_to_pending",
        task_file=src.name,
        task_id=task_id,
        task_type=task_type,
    )
    print(
        f"[approve] APPROVED {src.name} -> vault/Pending_Approval/ "
        f"(id={task_id[:8]}..., type={task_type})"
    )
    return 0


def cmd_reject(task_file_or_id: str, reason: str = "") -> int:
    src = _resolve_waiting_target(task_file_or_id)
    if src is None:
        print(f"[approve] Not found in Waiting_Approval: {task_file_or_id}")
        return 1

    dest = REJECTED_DIR / src.name
    if dest.exists():
        print(f"[approve] Destination already exists: {dest.name}")
        return 1

    manifest = _read_manifest(src)
    task_id = str(manifest.get("id", "unknown"))
    task_type = str(manifest.get("task_type", "unknown"))

    # Preserve JSON and annotate rejection metadata for audit readability.
    if manifest:
        manifest["status"] = "rejected"
        manifest["rejected_at"] = _utc_now()
        if reason:
            manifest["rejection_reason"] = reason
        tmp = REJECTED_DIR / (src.name + ".tmp")
        tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            src.unlink()
            tmp.rename(dest)
        except OSError as exc:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            print(f"[approve] Reject move failed: {exc}")
            return 1
    else:
        try:
            src.rename(dest)  # atomic move fallback
        except OSError as exc:
            print(f"[approve] Reject move failed: {exc}")
            return 1

    _append_log(
        action="rejected_waiting_to_rejected",
        task_file=src.name,
        task_id=task_id,
        task_type=task_type,
        reason=reason,
    )
    reason_text = f" | reason={reason}" if reason else ""
    print(
        f"[approve] REJECTED {src.name} -> vault/Rejected/ "
        f"(id={task_id[:8]}..., type={task_type}){reason_text}"
    )
    return 0


def main() -> int:
    _ensure_dirs()

    parser = argparse.ArgumentParser(
        prog="approve",
        description="HITL gate CLI for Waiting_Approval -> Pending_Approval/Rejected.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List tasks in vault/Waiting_Approval/.")
    sub.add_parser("status", help="Show queue counts.")

    p_approve = sub.add_parser("approve", help="Approve one task into Pending_Approval.")
    p_approve.add_argument("task_file_or_id", help="task_<uuid>.json, full UUID, or short task id prefix")

    p_reject = sub.add_parser("reject", help="Reject one task into Rejected.")
    p_reject.add_argument("task_file_or_id", help="task_<uuid>.json, full UUID, or short task id prefix")
    p_reject.add_argument("reason", nargs="?", default="", help="Optional rejection reason")

    args = parser.parse_args()

    if args.command == "list":
        return cmd_list()
    if args.command == "status":
        return cmd_status()
    if args.command == "approve":
        return cmd_approve(args.task_file_or_id)
    if args.command == "reject":
        return cmd_reject(args.task_file_or_id, args.reason)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
