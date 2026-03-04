"""
AI Employee Vault – Platinum Tier
Evidence Pack Generator

Script:  scripts/generate_evidence_pack.py
Version: 1.0.0

Responsibility:
    Reads live system state and produces a single judge-ready markdown
    file at Evidence/JUDGE_PROOF.md that captures:

        - UTC timestamp of generation
        - Count of tasks in vault/Pending_Approval/
        - Count of tasks in vault/Done/
        - Last 5 entries from vault/Logs/execution_log.json
        - Last N entries from history/prompt_log.json (default N=20),
          condensed to the last 5 for the summary table

    Every invocation is itself logged to history/prompt_log.json through
    the Platinum prompt logging subsystem.

Usage (from project root):
    python scripts/generate_evidence_pack.py
    python scripts/generate_evidence_pack.py --n 50
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys as _sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve project root — this script lives one level below it.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Guarantee required directories exist before any I/O.
# ---------------------------------------------------------------------------

for _d in [
    "vault/Pending_Approval",
    "vault/Done",
    "vault/Logs",
    "history",
    "logging",
    "scripts",
]:
    try:
        (_PROJECT_ROOT / _d).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # read-only filesystem on HF Spaces — vault dirs are optional

# ---------------------------------------------------------------------------
# Bootstrap prompt_logger (avoid stdlib logging/ name collision).
# ---------------------------------------------------------------------------

_pl_spec = importlib.util.spec_from_file_location(
    "prompt_logger",
    _PROJECT_ROOT / "logging" / "prompt_logger.py",
)
_pl_mod = importlib.util.module_from_spec(_pl_spec)
_sys.modules.setdefault("prompt_logger", _pl_mod)
_pl_spec.loader.exec_module(_pl_mod)

PromptLogger = _pl_mod.PromptLogger
EventType    = _pl_mod.EventType
Component    = _pl_mod.Component

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PENDING_DIR    = _PROJECT_ROOT / "vault" / "Pending_Approval"
_DONE_DIR       = _PROJECT_ROOT / "vault" / "Done"
# Log files live in the writable log dir (env-overridable; default /tmp on HF)
_LOG_DIR        = Path(os.environ.get("VAULT_LOG_DIR",  "/tmp/vault/Logs"))
_EXEC_LOG       = _LOG_DIR / "execution_log.json"
_PROMPT_LOG     = Path(os.environ.get("PROMPT_LOG_PATH", str(_LOG_DIR / "prompt_chain.json")))
_EVIDENCE_DIR   = Path(os.environ.get("EVIDENCE_OUT_DIR", "/tmp/evidence"))
os.makedirs(_EVIDENCE_DIR, exist_ok=True)
_OUTPUT_FILE    = _EVIDENCE_DIR / "JUDGE_PROOF.md"


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def _read_jsonl_tail(path: Path, n: int) -> list[dict]:
    """Return the last *n* valid JSON objects from a JSONL file."""
    if not path.exists():
        return []
    records: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except OSError:
        return []
    return records[-n:]


def _count_task_files(directory: Path) -> int:
    """Count task_*.json files in *directory*."""
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.glob("task_*.json"))


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------


def _build_markdown(
    generated_at: str,
    pending_count: int,
    done_count: int,
    exec_entries: list[dict],
    prompt_entries: list[dict],
    n_requested: int,
) -> str:
    lines: list[str] = []

    lines += [
        "# AI Employee Vault – Platinum Tier",
        "## Judge Verification Evidence Pack",
        "",
        f"> **Generated:** {generated_at} UTC  ",
        f"> **Script:** `scripts/generate_evidence_pack.py`  ",
        f"> **Prompt log entries read:** last {n_requested}",
        "",
        "---",
        "",
        "## 1. Vault State",
        "",
        "| Directory | Task count |",
        "|---|---|",
        f"| `vault/Pending_Approval/` | {pending_count} |",
        f"| `vault/Done/` | {done_count} |",
        "",
        "---",
        "",
        "## 2. Last 5 Execution Log Entries",
        "",
    ]

    if exec_entries:
        lines += [
            "| # | id (short) | task_type | action | timestamp |",
            "|---|---|---|---|---|",
        ]
        for i, e in enumerate(exec_entries, 1):
            tid      = e.get("id", "n/a")[:8] + "..."
            ttype    = e.get("task_type", "n/a")
            action   = e.get("action", "n/a")
            ts       = e.get("timestamp", "n/a")
            lines.append(f"| {i} | `{tid}` | `{ttype}` | `{action}` | {ts} |")
    else:
        lines.append("_No execution log entries found._")

    lines += [
        "",
        "---",
        "",
        "## 3. Last 5 Prompt History Entries",
        "",
    ]

    if prompt_entries:
        lines += [
            "| # | timestamp | component | event_type | summary |",
            "|---|---|---|---|---|",
        ]
        for i, e in enumerate(prompt_entries, 1):
            ts        = e.get("timestamp", "n/a")
            component = e.get("component", "n/a")
            etype     = e.get("event_type", "n/a")
            summary   = e.get("content", {}).get("summary", "n/a")
            # Truncate long summaries for table legibility
            if len(summary) > 80:
                summary = summary[:77] + "..."
            lines.append(f"| {i} | {ts} | `{component}` | `{etype}` | {summary} |")
    else:
        lines.append("_No prompt history entries found._")

    lines += [
        "",
        "---",
        "",
        "## 4. Integrity Statement",
        "",
        "This evidence pack was generated by reading live filesystem state.",
        "All prompt log entries are SHA-256 hash-chained (see `logging/prompt_logger.py`).",
        "Execution log entries are append-only JSONL with `os.fsync()` durability.",
        "",
        "_This file is regenerated on every invocation of_",
        "`scripts/generate_evidence_pack.py` _and is not manually edited._",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate(n: int = 20) -> Path:
    """
    Generate Evidence/JUDGE_PROOF.md and log the event.

    Args:
        n: Number of prompt log entries to read (last N lines).

    Returns:
        Path to the generated markdown file.
    """
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

    # --- Collect data ---
    pending_count  = _count_task_files(_PENDING_DIR)
    done_count     = _count_task_files(_DONE_DIR)
    exec_entries   = _read_jsonl_tail(_EXEC_LOG, 5)
    all_prompt     = _read_jsonl_tail(_PROMPT_LOG, n)
    prompt_entries = all_prompt[-5:]

    # --- Build markdown ---
    content = _build_markdown(
        generated_at=generated_at,
        pending_count=pending_count,
        done_count=done_count,
        exec_entries=exec_entries,
        prompt_entries=prompt_entries,
        n_requested=n,
    )

    # --- Write output ---
    _OUTPUT_FILE.write_text(content, encoding="utf-8")

    # --- Log the event ---
    logger = PromptLogger(component=Component.SYSTEM)
    logger.log(
        event_type=EventType.RESULT_PROCESSED,
        summary="Evidence pack generated",
        detail=(
            f"Output: {_OUTPUT_FILE} | "
            f"pending={pending_count} | done={done_count} | "
            f"exec_entries={len(exec_entries)} | prompt_entries_read={len(all_prompt)}"
        ),
        metadata_extra={
            "output_file":     str(_OUTPUT_FILE),
            "pending_count":   pending_count,
            "done_count":      done_count,
            "exec_entries":    len(exec_entries),
            "prompt_n":        n,
            "generated_at":    generated_at,
        },
    )
    logger.log(
        event_type=EventType.SYSTEM_SHUTDOWN,
        summary="Evidence generator complete",
        detail=f"JUDGE_PROOF.md written at {generated_at}",
    )

    return _OUTPUT_FILE


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="generate_evidence_pack",
        description=(
            "AI Employee Vault - Platinum Tier: Evidence Pack Generator.\n"
            "Produces Evidence/JUDGE_PROOF.md from live system state."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--n",
        type=int,
        default=20,
        metavar="N",
        help="Number of prompt log entries to read (default: 20).",
    )

    args = parser.parse_args()

    out = generate(n=args.n)

    print(f"[EvidencePack] JUDGE_PROOF.md written -> {out}")
    print(f"[EvidencePack] Logged to history/prompt_log.json")
