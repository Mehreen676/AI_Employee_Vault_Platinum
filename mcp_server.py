"""
MCP-style tool server for Silver Agent.

Provides two callable tools used by agent.py instead of direct file operations:
  - list_tasks(folder)  : returns list of *.md filenames in folder
  - move_task(src, dst) : moves a file from src to dst, returns success bool

Now also supports:
  - Running in standalone "server mode" for demonstration.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def list_tasks(folder: str | Path) -> list[str]:
    """Return sorted list of *.md filenames in folder (excluding .gitkeep)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(
        f.name for f in folder.glob("*.md") if f.name != ".gitkeep"
    )


def move_task(src: str | Path, dst: str | Path) -> bool:
    """Move file src to dst (file or directory). Returns True on success."""
    src, dst = Path(src), Path(dst)

    if not src.exists():
        return False

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return True
    except Exception:
        return False


# --------------------------
# Server Mode (Demo Purpose)
# --------------------------
if __name__ == "__main__":
    print("=== MCP Tool Server Running ===")
    print("Available tools:")
    print(" - list_tasks(folder)")
    print(" - move_task(src, dst)")
    print("Server ready (local mode).")
