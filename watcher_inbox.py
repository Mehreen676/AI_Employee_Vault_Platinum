"""Watcher 1 – Inbox to Needs_Action.

Moves any *.md files from Inbox/ to Needs_Action/.
Logs each move to run_log.md with UTC timestamp.
Safe: creates folders if missing, never crashes.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
INBOX = BASE_DIR / "Inbox"
NEEDS_ACTION = BASE_DIR / "Needs_Action"
RUN_LOG = BASE_DIR / "run_log.md"


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def append_log(text: str) -> None:
    with open(RUN_LOG, "a", encoding="utf-8") as f:
        f.write(text)


def main() -> None:
    print("=== Watcher Inbox Running ===")

    INBOX.mkdir(parents=True, exist_ok=True)
    NEEDS_ACTION.mkdir(parents=True, exist_ok=True)

    files = sorted(INBOX.glob("*.md"))
    files = [f for f in files if f.name != ".gitkeep"]

    if not files:
        print("No files in Inbox/.")
        return

    for f in files:
        dest = NEEDS_ACTION / f.name
        try:
            dest.write_bytes(f.read_bytes())
            f.unlink()
            append_log(f"{utc_ts()} - Watcher_Inbox: moved {f.name} -> Needs_Action/\n")
            print(f"Moved: {f.name} -> Needs_Action/")
        except Exception as e:
            print(f"Error moving {f.name}: {e}")

    print("=== Watcher Inbox Done ===")


if __name__ == "__main__":
    main()
