"""
AI Employee Vault - Platinum Tier
Root-level Local Executor entry point.

Usage:
    python local_executor.py --poll 2
    python local_executor.py --once
    python local_executor.py --help

Delegates to local_executor/executor.py.
All vault directories and history/ are created here if missing,
before any package code runs.
"""

import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root is the directory that contains this script.
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Guarantee all required directories exist before anything else touches them.
# This is the single authoritative directory-creation point for the
# Local Executor process.
# ---------------------------------------------------------------------------

for _dir in [
    "vault/Waiting_Approval",
    "vault/Pending_Approval",
    "vault/Rejected",
    "vault/Approved",
    "vault/Done",
    "vault/Logs",
    "vault/Needs_Action/email",
    "vault/In_Progress/cloud",
    "vault/In_Progress/local",
    "vault/Updates",
    "history",
    "logging",
]:
    (_ROOT / _dir).mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so that intra-package imports
# inside local_executor/ resolve correctly.
# ---------------------------------------------------------------------------

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Load local_executor/executor.py as the __main__ module so that its
# `if __name__ == "__main__":` block executes with the current sys.argv.
# importlib.util is used rather than a direct import so that the file
# named "local_executor.py" (this script) does not shadow the local_executor/
# package when Python resolves `import local_executor`.
# ---------------------------------------------------------------------------

_executor_path = _ROOT / "local_executor" / "executor.py"

if not _executor_path.exists():
    print(f"[local_executor.py] ERROR: cannot find {_executor_path}")
    sys.exit(1)

_spec = importlib.util.spec_from_file_location("__main__", _executor_path)
_mod = importlib.util.module_from_spec(_spec)

# Set __file__ so that _PROJECT_ROOT resolution inside executor.py is correct.
_mod.__file__ = str(_executor_path)

_spec.loader.exec_module(_mod)
