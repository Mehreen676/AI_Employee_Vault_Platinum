"""
HITL Approval CLI — Gold Tier.

Manages files in Pending_Approval/, Approved/, and Rejected/.

Usage:
  python approve.py                               # list all pending HITL requests
  python approve.py <hitl_filename.md>            # approve one file
  python approve.py --all                         # approve all pending
  python approve.py --reject <hitl_filename.md>   # reject one file
  python approve.py --reject --all                # reject all pending
  python approve.py --reject <filename> --reason "Too risky"

How the pipeline works:
  Pending_Approval/hitl_*.md  ← approval request (YAML frontmatter)
  Pending_Approval/<task>.md  ← original task held here

  approve.py approve  -> moves hitl file to Approved/   -> agent resumes task
  approve.py reject   -> moves hitl file to Rejected/   -> agent archives task
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

from mcp_file_ops import list_tasks

BASE_DIR = Path(__file__).resolve().parent
PENDING = BASE_DIR / "Pending_Approval"
APPROVED = BASE_DIR / "Approved"
REJECTED = BASE_DIR / "Rejected"
RUN_LOG = BASE_DIR / "run_log.md"


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def append_log(text: str) -> None:
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RUN_LOG, "a", encoding="utf-8") as f:
        f.write(text)


def list_hitl_pending() -> list[str]:
    """Return sorted list of hitl_*.md files in Pending_Approval/."""
    PENDING.mkdir(parents=True, exist_ok=True)
    return sorted(f.name for f in PENDING.glob("hitl_*.md"))


def _update_status_in_content(content: str, new_status: str, reason: str = "") -> str:
    """Replace status: value in YAML frontmatter block."""
    lines = content.split("\n")
    result = []
    in_front = False
    status_replaced = False
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_front = True
            result.append(line)
            continue
        if in_front and line.strip() == "---":
            # Inject rejection_reason before closing --- if rejecting
            if reason and new_status == "rejected":
                result.append(f'rejection_reason: "{reason}"')
            in_front = False
            result.append(line)
            continue
        if in_front and line.startswith("status:") and not status_replaced:
            result.append(f"status: {new_status}")
            status_replaced = True
            continue
        result.append(line)
    return "\n".join(result)


def approve_file(filename: str) -> bool:
    """Move a hitl file from Pending_Approval/ to Approved/."""
    src = PENDING / filename
    if not src.exists():
        print(f"  Not found in Pending_Approval/: {filename}")
        return False

    if not filename.startswith("hitl_"):
        print(f"  Skipping non-HITL file: {filename} (must start with hitl_)")
        return False

    APPROVED.mkdir(parents=True, exist_ok=True)
    dst = APPROVED / filename

    # Update status in file content before moving
    try:
        content = src.read_text(encoding="utf-8")
        updated = _update_status_in_content(content, "approved")
        dst.write_text(updated, encoding="utf-8")
        src.unlink()
    except Exception as e:
        print(f"  Error moving {filename}: {e}")
        return False

    append_log(f"{utc_ts()} - HITL Approved: {filename} -> Approved/\n")
    print(f"  Approved: {filename} -> Approved/")
    print(f"  Next: run 'python gold_agent.py' to process the approved task.")
    return True


def reject_file(filename: str, reason: str = "") -> bool:
    """Move a hitl file from Pending_Approval/ to Rejected/."""
    src = PENDING / filename
    if not src.exists():
        print(f"  Not found in Pending_Approval/: {filename}")
        return False

    if not filename.startswith("hitl_"):
        print(f"  Skipping non-HITL file: {filename} (must start with hitl_)")
        return False

    REJECTED.mkdir(parents=True, exist_ok=True)
    dst = REJECTED / filename

    reason_text = reason or "No reason provided"

    try:
        content = src.read_text(encoding="utf-8")
        updated = _update_status_in_content(content, "rejected", reason=reason_text)
        dst.write_text(updated, encoding="utf-8")
        src.unlink()
    except Exception as e:
        print(f"  Error moving {filename}: {e}")
        return False

    append_log(f"{utc_ts()} - HITL Rejected: {filename} -> Rejected/ | reason={reason_text}\n")
    print(f"  Rejected: {filename} -> Rejected/ (reason: {reason_text})")
    print(f"  Next: run 'python gold_agent.py' to archive the rejected task.")
    return True


def show_pending() -> None:
    """Print all pending HITL requests with a summary."""
    pending = list_hitl_pending()
    if not pending:
        print("No HITL approval requests pending.")
        return

    print(f"Pending HITL approval requests ({len(pending)}):\n")
    for name in pending:
        path = PENDING / name
        try:
            content = path.read_text(encoding="utf-8")
            # Quick extract of action and task_file from frontmatter
            action = ""
            task_file = ""
            for line in content.split("\n")[1:]:
                if line.strip() == "---":
                    break
                if line.startswith("action:"):
                    action = line.split(":", 1)[1].strip()
                if line.startswith("task_file:"):
                    task_file = line.split(":", 1)[1].strip()
            print(f"  {name}")
            print(f"    action={action}  task={task_file}")
        except Exception:
            print(f"  {name}")

    print(f"\nApprove:  python approve.py <filename>")
    print(f"Reject:   python approve.py --reject <filename> [--reason \"text\"]")
    print(f"All:      python approve.py --all  |  python approve.py --reject --all")


def main() -> None:
    PENDING.mkdir(parents=True, exist_ok=True)
    APPROVED.mkdir(parents=True, exist_ok=True)
    REJECTED.mkdir(parents=True, exist_ok=True)

    args = sys.argv[1:]

    # No args — list mode
    if not args:
        show_pending()
        return

    # Parse flags
    is_reject = "--reject" in args
    is_all = "--all" in args
    reason = ""
    if "--reason" in args:
        idx = args.index("--reason")
        if idx + 1 < len(args):
            reason = args[idx + 1]

    # Strip flags to get filename(s)
    filename_args = [
        a for a in args
        if not a.startswith("--") and a != reason
    ]
    filename = filename_args[0] if filename_args else ""

    pending = list_hitl_pending()

    if is_all:
        if not pending:
            print("No HITL requests pending.")
            return
        action_fn = reject_file if is_reject else approve_file
        for name in pending:
            if is_reject:
                action_fn(name, reason)
            else:
                action_fn(name)
        return

    if not filename:
        show_pending()
        return

    if is_reject:
        reject_file(filename, reason)
    else:
        approve_file(filename)


if __name__ == "__main__":
    main()
