"""
MCP Server 1 – File Operations.

Handles all vault file CRUD: list, read, write, move, delete tasks.
Used by the Gold agent for cross-domain file management.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from audit_logger import log_action

SERVER_NAME = "mcp_file_ops"


def list_tasks(folder: str | Path, extension: str = "*.md") -> list[str]:
    """Return sorted list of task filenames in folder (excluding .gitkeep)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    results = sorted(f.name for f in folder.glob(extension) if f.name != ".gitkeep")
    log_action(SERVER_NAME, "list_tasks", {"folder": str(folder), "count": len(results)})
    return results


def read_task(file_path: str | Path) -> str:
    """Read and return file contents. Returns empty string on failure."""
    file_path = Path(file_path)
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        log_action(SERVER_NAME, "read_task", {"file": str(file_path), "chars": len(content)})
        return content
    except Exception as e:
        log_action(SERVER_NAME, "read_task_error", {"file": str(file_path), "error": str(e)}, success=False)
        return ""


def write_task(file_path: str | Path, content: str) -> bool:
    """Write content to file. Creates parent dirs if needed."""
    file_path = Path(file_path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        log_action(SERVER_NAME, "write_task", {"file": str(file_path), "chars": len(content)})
        return True
    except Exception as e:
        log_action(SERVER_NAME, "write_task_error", {"file": str(file_path), "error": str(e)}, success=False)
        return False


def move_task(src: str | Path, dst: str | Path) -> bool:
    """Move file from src to dst. Returns True on success."""
    src, dst = Path(src), Path(dst)
    if not src.exists():
        log_action(SERVER_NAME, "move_task_error", {"src": str(src), "reason": "src_not_found"}, success=False)
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        log_action(SERVER_NAME, "move_task", {"src": str(src), "dst": str(dst)})
        return True
    except Exception as e:
        log_action(SERVER_NAME, "move_task_error", {"src": str(src), "error": str(e)}, success=False)
        return False


def delete_task(file_path: str | Path) -> bool:
    """Delete a task file. Returns True on success."""
    file_path = Path(file_path)
    try:
        file_path.unlink(missing_ok=True)
        log_action(SERVER_NAME, "delete_task", {"file": str(file_path)})
        return True
    except Exception as e:
        log_action(SERVER_NAME, "delete_task_error", {"file": str(file_path), "error": str(e)}, success=False)
        return False


if __name__ == "__main__":
    print(f"=== {SERVER_NAME} Server Ready ===")
    print("Tools: list_tasks, read_task, write_task, move_task, delete_task")
