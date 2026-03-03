"""
AI Employee Vault - Platinum Tier
Root-level Cloud Agent entry point.

Usage:
    python cloud_agent.py --auto
    python cloud_agent.py --auto --interval 5
    python cloud_agent.py --help

Delegates to cloud_agent/agent.py.
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
# Cloud Agent process.
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
# inside cloud_agent/ resolve correctly.
# ---------------------------------------------------------------------------

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Load cloud_agent/agent.py as the __main__ module so that its
# `if __name__ == "__main__":` block executes with the current sys.argv.
# importlib.util is used rather than a direct import so that the file
# named "cloud_agent.py" (this script) does not shadow the cloud_agent/
# package when Python resolves `import cloud_agent`.
# ---------------------------------------------------------------------------

_agent_path = _ROOT / "cloud_agent" / "agent.py"

if not _agent_path.exists():
    print(f"[cloud_agent.py] ERROR: cannot find {_agent_path}")
    sys.exit(1)

_spec = importlib.util.spec_from_file_location("__main__", _agent_path)
_mod = importlib.util.module_from_spec(_spec)

# Set __file__ so that _PROJECT_ROOT resolution inside agent.py is correct.
_mod.__file__ = str(_agent_path)

_spec.loader.exec_module(_mod)
