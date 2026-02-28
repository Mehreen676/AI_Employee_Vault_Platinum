"""
HITL (Human-in-the-Loop) – Gold Tier.

Responsibilities:
  1. Detect sensitive actions in task content.
  2. Write an approval request (YAML frontmatter + markdown) to Pending_Approval/.
  3. Move the original task out of Needs_Action/ into Pending_Approval/ to pause it.
  4. Process files that appear in Approved/ — resume them through the normal pipeline.
  5. Process files that appear in Rejected/ — archive with rejection note to Done/.

Approval request filename pattern:  hitl_<timestamp>_<original_name>
Original task is held at:           Pending_Approval/<original_name>
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Callable

from audit_logger import log_action

SERVER_NAME = "hitl"

# ── Sensitive keyword → action-type mapping ──────────────────────────────────
_SENSITIVE: list[tuple[str, str]] = [
    # (regex pattern, action_type)
    (r"\bsend\s+email\b",           "email_send"),
    (r"\bemail\s+blast\b",          "email_send"),
    (r"\bpayment\b",                "payment"),
    (r"\bwire\s+transfer\b",        "payment"),
    (r"\binvoice\s+pay\b",          "payment"),
    (r"\bcharge\s+card\b",          "payment"),
    (r"\bpurchase\b",               "payment"),
    (r"\bpost\s+to\b",              "publish"),
    (r"\bpublish\b",                "publish"),
    (r"\bbroadcast\b",              "publish"),
    (r"\bannouncement\b",           "publish"),
    (r"\bdeploy\s+to\s+prod\b",     "deploy"),
    (r"\bpush\s+to\s+production\b", "deploy"),
    (r"\bgo[\s-]?live\b",          "deploy"),
    (r"\brelease\s+to\s+prod\b",    "deploy"),
    (r"\bdelete\s+all\b",           "delete"),
    (r"\bpurge\b",                  "delete"),
    (r"\bdrop\s+table\b",           "delete"),
    (r"\bsubmit\s+form\b",          "browser_action"),
    (r"\bclick\s+confirm\b",        "browser_action"),
    (r"\bauto[\s-]?click\b",        "browser_action"),
    (r"\bauthorize\b",              "authorize"),
    (r"\bapprove\s+transaction\b",  "authorize"),
    (r"\bslack\s+message\b",        "notify_external"),
    (r"\bwebhook\b",                "notify_external"),
]


def detect_sensitive(content: str) -> tuple[bool, str, list[str]]:
    """
    Scan task content for sensitive-action patterns.

    Returns:
        (is_sensitive, primary_action_type, list_of_matched_keywords)
    """
    text = content.lower()
    matched_keywords: list[str] = []
    primary_action = ""

    for pattern, action_type in _SENSITIVE:
        if re.search(pattern, text):
            keyword = pattern.replace(r"\b", "").replace("\\s+", " ").replace("\\", "")
            matched_keywords.append(keyword.strip())
            if not primary_action:
                primary_action = action_type

    is_sensitive = bool(matched_keywords)
    log_action(
        SERVER_NAME,
        "detect_sensitive",
        {"is_sensitive": is_sensitive, "action": primary_action, "keywords": matched_keywords},
    )
    return is_sensitive, primary_action, matched_keywords


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_iso(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _approval_filename(original_name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"hitl_{ts}_{original_name}"


def request_approval(
    task_name: str,
    original_content: str,
    domain: str,
    action_type: str,
    matched_keywords: list[str],
    base_dir: Path,
    run_id: int | None = None,
) -> str:
    """
    Pause a sensitive task and request human approval.

    Steps:
      1. Move original from Needs_Action/ → Pending_Approval/<task_name>
      2. Write HITL approval request to Pending_Approval/<hitl_filename>

    Returns the hitl approval request filename.
    """
    needs_action = base_dir / "Needs_Action"
    pending = base_dir / "Pending_Approval"
    pending.mkdir(parents=True, exist_ok=True)

    src = needs_action / task_name
    held_dst = pending / task_name

    # Move original to Pending_Approval/ (held, not processed)
    if src.exists():
        shutil.move(str(src), str(held_dst))

    # Build YAML frontmatter approval request
    payload_summary = original_content[:300].replace("\n", " ").replace('"', "'")
    hitl_filename = _approval_filename(task_name)

    approval_content = f"""---
type: hitl_approval_request
action: {action_type}
task_file: {task_name}
domain: {domain}
status: pending_approval
created: {_now_iso()}
expires: {_expires_iso(24)}
run_id: {run_id}
sensitive_keywords:
{chr(10).join(f'  - {kw}' for kw in matched_keywords)}
payload_summary: "{payload_summary}"
---

# HITL Approval Request

**Action requiring approval:** `{action_type}`
**Task file:** `{task_name}`
**Domain:** {domain.title()}
**Created:** {_now_iso()}
**Expires:** {_expires_iso(24)}
**Run ID:** {run_id}

## Why This Needs Approval

The task contains sensitive keywords that require human sign-off before execution:

{chr(10).join(f'- `{kw}`' for kw in matched_keywords)}

## Task Summary

```
{original_content[:500]}
```

## How to Respond

**Approve** (resume task through pipeline):
```bash
python approve.py {hitl_filename}
```

**Reject** (cancel and archive):
```bash
python approve.py --reject {hitl_filename}
python approve.py --reject {hitl_filename} --reason "Too risky at this time"
```

**Approve all pending:**
```bash
python approve.py --all
```

---
*Generated by AI Employee Vault — Gold Tier HITL Module*
"""

    (pending / hitl_filename).write_text(approval_content, encoding="utf-8")

    log_action(SERVER_NAME, "approval_requested", {
        "hitl_file": hitl_filename,
        "task_file": task_name,
        "action": action_type,
        "domain": domain,
        "run_id": run_id,
    })
    print(f"  [HITL] Approval requested: {hitl_filename}")
    return hitl_filename


def _parse_yaml_frontmatter(content: str) -> dict:
    """
    Extract simple key: value pairs from a YAML frontmatter block.
    Handles scalars and basic lists (  - item).
    No external dependency (pure stdlib).
    """
    result: dict = {}
    if not content.startswith("---"):
        return result

    lines = content.split("\n")
    in_front = False
    current_list_key: str | None = None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("  - ") and current_list_key:
            result.setdefault(current_list_key, []).append(line.strip()[2:])
            continue
        if ":" in line and not line.startswith(" "):
            current_list_key = None
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val == "":
                current_list_key = key
                result[key] = []
            else:
                result[key] = val

    return result


def list_hitl_files(folder: Path) -> list[str]:
    """Return sorted list of hitl_*.md files in a folder."""
    if not folder.is_dir():
        return []
    return sorted(f.name for f in folder.glob("hitl_*.md"))


def process_approvals(
    base_dir: Path,
    run_id: int | None,
    resume_task_fn: Callable[[str, str, Path], bool],
    dispatch_fn: Callable[[str, dict], None] | None = None,
) -> int:
    """
    Scan Approved/ for hitl_*.md files and resume each approved task.

    For each approved hitl file:
      1. Parse YAML frontmatter to get task_file and domain.
      2. Find original in Pending_Approval/<task_file>.
      3. Dispatch approved action to MCP stub (if dispatch_fn provided).
      4. Move original back to Needs_Action/ so normal pipeline processes it.
      5. Archive hitl file to Done/ with approved_ prefix.

    resume_task_fn(task_name, domain, base_dir) → bool (success)
    dispatch_fn(action_type, payload_dict) → None  (optional MCP stub call)

    Returns count of successfully processed approvals.
    """
    approved_dir = base_dir / "Approved"
    pending_dir = base_dir / "Pending_Approval"
    needs_action = base_dir / "Needs_Action"
    done_dir = base_dir / "Done"

    approved_dir.mkdir(parents=True, exist_ok=True)
    done_dir.mkdir(parents=True, exist_ok=True)

    hitl_files = list_hitl_files(approved_dir)
    if not hitl_files:
        return 0

    processed = 0
    for hitl_name in hitl_files:
        hitl_path = approved_dir / hitl_name
        content = hitl_path.read_text(encoding="utf-8", errors="ignore")
        meta = _parse_yaml_frontmatter(content)

        task_file = meta.get("task_file", "")
        domain = meta.get("domain", "business")
        action = meta.get("action", "unknown")

        if not task_file:
            log_action(SERVER_NAME, "approval_skip_no_task_file",
                       {"hitl": hitl_name}, success=False)
            continue

        original_path = pending_dir / task_file
        if not original_path.exists():
            log_action(SERVER_NAME, "approval_skip_original_missing",
                       {"hitl": hitl_name, "task_file": task_file}, success=False)
            # Archive the stale hitl file anyway
            shutil.move(str(hitl_path), str(done_dir / f"approved_{hitl_name}"))
            continue

        # ── STAGE 1: APPROVED ─────────────────────────────────────────────────
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  [HITL] [OK] APPROVED")
        print(f"  [HITL]   action   : {action}")
        print(f"  [HITL]   task     : {task_file}")
        print(f"  [HITL]   domain   : {domain}")
        print(f"  [HITL]   hitl_file: {hitl_name}")
        print(f"  [HITL]   run_id   : {run_id}")
        print(sep)

        # ── STAGE 2: TOOL CALLED ──────────────────────────────────────────────
        dispatch_result: dict = {}
        if dispatch_fn is not None:
            try:
                dispatch_result = dispatch_fn(action, {
                    "task_file": task_file,
                    "domain": domain,
                    "run_id": run_id,
                    "hitl": hitl_name,
                }) or {}
            except Exception as _exc:
                dispatch_result = {"result": "dispatch_error", "message": str(_exc)}

        server_name = dispatch_result.get("server", "none")
        tool_result = dispatch_result.get("result", "no_handler")
        dry_run_flag = dispatch_result.get("dry_run", True)
        print(f"  [HITL] -> TOOL CALLED : {action!r} -> {server_name}"
              f"  (dry_run={dry_run_flag})")
        print(f"  [HITL] -> TOOL RESULT : {tool_result}")

        # ── STAGE 3: RESULT LOGGED ────────────────────────────────────────────
        log_action(SERVER_NAME, "approval_processed", {
            "hitl": hitl_name,
            "task_file": task_file,
            "action": action,
            "domain": domain,
            "run_id": run_id,
            "dispatch_server": server_name,
            "dispatch_result": tool_result,
            "dry_run": dry_run_flag,
        })
        print(f"  [HITL] -> RESULT LOGGED: audit_logger + Logs/<today>.json + DB events")

        # ── STAGE 4: TASK RESUMED -> MOVED TO DONE ───────────────────────────
        # Move original back to Needs_Action for normal processing
        shutil.move(str(original_path), str(needs_action / task_file))
        print(f"  [HITL] -> TASK RESUMED : {task_file} -> Needs_Action/")

        # Call the pipeline function
        ok = resume_task_fn(task_file, domain, base_dir)

        # Archive approval file
        archive_name = f"approved_{hitl_name}"
        shutil.move(str(hitl_path), str(done_dir / archive_name))
        print(f"  [HITL] -> MOVED TO DONE: Done/{archive_name}")

        status_icon = "[OK] COMPLETED" if ok else "[FAIL] FAILED"
        print(f"  [HITL] -> PIPELINE    : {status_icon}")
        print(sep + "\n")

        if ok:
            processed += 1

    return processed


def process_rejections(base_dir: Path, run_id: int | None) -> int:
    """
    Scan Rejected/ for hitl_*.md files and archive each rejected task.

    For each rejected hitl file:
      1. Parse YAML to get task_file and rejection reason.
      2. Find original in Pending_Approval/<task_file>.
      3. Write rejection summary to Done/ with rejected_ prefix.
      4. Archive hitl file to Done/ with rejected_hitl_ prefix.

    Returns count of rejections processed.
    """
    rejected_dir = base_dir / "Rejected"
    pending_dir = base_dir / "Pending_Approval"
    done_dir = base_dir / "Done"

    rejected_dir.mkdir(parents=True, exist_ok=True)
    done_dir.mkdir(parents=True, exist_ok=True)

    hitl_files = list_hitl_files(rejected_dir)
    if not hitl_files:
        return 0

    processed = 0
    for hitl_name in hitl_files:
        hitl_path = rejected_dir / hitl_name
        content = hitl_path.read_text(encoding="utf-8", errors="ignore")
        meta = _parse_yaml_frontmatter(content)

        task_file = meta.get("task_file", "")
        domain = meta.get("domain", "business")
        action = meta.get("action", "unknown")
        reason = meta.get("rejection_reason", "No reason provided")

        # Write rejection summary to Done/
        if task_file:
            original_path = pending_dir / task_file
            original_content = ""
            if original_path.exists():
                original_content = original_path.read_text(encoding="utf-8", errors="ignore")
                original_path.unlink()

            rejection_note = (
                "# Rejected Task (Gold Tier HITL)\n\n"
                f"**Task:** {task_file}\n"
                f"**Domain:** {domain.title()}\n"
                f"**Action type:** {action}\n"
                f"**Rejected at:** {_now_iso()}\n"
                f"**Reason:** {reason}\n"
                f"**Run ID:** {run_id}\n\n"
                "## Original Content\n"
                f"{original_content[:1000] or '(not found)'}\n\n"
                "Status: Rejected\n"
            )
            (done_dir / f"rejected_{task_file}").write_text(rejection_note, encoding="utf-8")

        # Archive rejection hitl file
        shutil.move(str(hitl_path), str(done_dir / f"rejected_hitl_{hitl_name}"))

        log_action(SERVER_NAME, "rejection_processed", {
            "hitl": hitl_name,
            "task_file": task_file,
            "reason": reason,
            "action": action,
            "run_id": run_id,
        })
        print(f"  [HITL] Rejected & archived: {task_file}")
        processed += 1

    return processed
