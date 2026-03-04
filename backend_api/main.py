"""
AI Employee Vault – Platinum Tier
FastAPI Backend API  |  v1.0.0

Exposes vault state, task queues, HITL approval, logs, and evidence
for a web dashboard frontend.  Deployable on HuggingFace Spaces (port 7860).

Environment variables:
  VAULT_ROOT      Absolute path to the repo root (default: parent of this file)
  ALLOWED_ORIGINS Comma-separated CORS origins   (default: *)
  PORT            Server port                     (default: 7860)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

# ── Configuration ─────────────────────────────────────────────────────────────

VERSION = "1.0.0"

# Resolve repo root: backend_api/ lives one level inside the repo
_HERE       = Path(__file__).resolve().parent
VAULT_ROOT  = Path(os.getenv("VAULT_ROOT", str(_HERE.parent)))
VAULT_DIR   = VAULT_ROOT / "vault"
# On HuggingFace Spaces /app is read-only; writable paths live under /tmp
EVIDENCE_DIR = Path(os.getenv("EVIDENCE_OUT_DIR", "/tmp/Evidence"))
LOG_DIR      = Path(os.getenv("VAULT_LOG_DIR",    "/tmp/vault/Logs"))
SCRIPTS_DIR  = VAULT_ROOT / "scripts"
HISTORY_DIR  = VAULT_ROOT / "history"

_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = (
    ["*"] if _origins_env.strip() == "*"
    else [o.strip() for o in _origins_env.split(",") if o.strip()]
)

# ── Queue directory map ────────────────────────────────────────────────────────

QUEUE_DIRS: dict[str, Path] = {
    "needs_action":     VAULT_DIR / "Needs_Action",
    "waiting_approval": VAULT_DIR / "Waiting_Approval",   # optional
    "pending_approval": VAULT_DIR / "Pending_Approval",
    "approved":         VAULT_DIR / "Approved",
    "done":             VAULT_DIR / "Done",
    "retry_queue":      VAULT_DIR / "Retry_Queue",
    "rejected":         VAULT_DIR / "Rejected",
}

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Employee Vault – Platinum Tier API",
    description=(
        "Production backend for the Platinum Tier distributed AI task management system. "
        "Exposes vault state, HITL approval, logs, and evidence generation."
    ),
    version=VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup initialisation ────────────────────────────────────────────────────

@app.on_event("startup")
def _startup_init() -> None:
    """
    Guarantee writable directories and seed log files on every cold start.

    HuggingFace Spaces: /app is read-only — all writes go to /tmp.
      LOG_DIR      = /tmp/vault/Logs   (VAULT_LOG_DIR env var)
      EVIDENCE_DIR = /tmp/Evidence     (EVIDENCE_OUT_DIR env var)

    All OSError exceptions are silently swallowed so the server always starts.
    """
    # Create writable directories
    for _d in (LOG_DIR, LOG_DIR.parent / "Queue", EVIDENCE_DIR):
        try:
            _d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    # Seed empty log files (JSONL — empty file = zero entries)
    for _fname in ("execution_log.json", "prompt_chain.json", "health_log.json"):
        _fpath = LOG_DIR / _fname
        try:
            if not _fpath.exists():
                _fpath.write_text("", encoding="utf-8")
        except OSError:
            pass


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"ok": True, "service": "ai-employee-vault-backend"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_filename(filename: str) -> str:
    """
    Validate filename to prevent path traversal.
    Raises HTTPException 400 on suspicious input.
    """
    p = Path(filename)
    # Must be a plain filename with no directory separators
    if p.name != filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    # Must end with a known extension
    if not filename.endswith((".json", ".md", ".txt")):
        raise HTTPException(status_code=400, detail="Unsupported file extension.")
    return filename


def _count_dir(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for f in path.iterdir() if f.is_file())


def _tail_jsonl(path: Path, n: int) -> list[dict]:
    """Return last n lines of a JSONL file as parsed dicts."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    result: list[dict] = []
    for line in lines[-n:]:
        line = line.strip()
        if line:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                result.append({"_raw": line})
    return result


def _tail_text(path: Path, n: int) -> list[str]:
    """Return last n non-empty lines of a text file."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [l for l in lines[-n:] if l.strip()]


def _parse_task(path: Path) -> dict[str, Any]:
    """Parse a task JSON file; return raw dict or error sentinel."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_parse_error": str(exc), "filename": path.name}


def _queue_path(name: str) -> Path:
    """Resolve a queue name to its directory path."""
    if name not in QUEUE_DIRS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown queue '{name}'. "
                   f"Valid: {', '.join(QUEUE_DIRS)}",
        )
    return QUEUE_DIRS[name]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """Basic liveness probe — returns 200 immediately."""
    return {
        "status": "ok",
        "time":    datetime.now(timezone.utc).isoformat(),
        "version": VERSION,
    }


@app.get("/status", tags=["System"])
def status():
    """
    Summarise the current vault state:
    - Task counts for all known queues
    - Last 5 lines of cloud_updates.md (Cloud Agent heartbeat)
    - Last 5 execution log entries
    """
    counts: dict[str, int] = {}
    for key, path in QUEUE_DIRS.items():
        counts[key] = _count_dir(path)

    cloud_updates = _tail_text(
        VAULT_DIR / "Updates" / "cloud_updates.md", 20
    )

    last_execution = _tail_jsonl(LOG_DIR / "execution_log.json", 5)

    last_health = _tail_jsonl(LOG_DIR / "health_log.json", 1)

    return {
        "vault_root":      str(VAULT_ROOT),
        "queues":          counts,
        "cloud_updates":   cloud_updates[-5:] if cloud_updates else [],
        "last_executions": last_execution,
        "last_health":     last_health[0] if last_health else None,
        "time":            datetime.now(timezone.utc).isoformat(),
    }


@app.get("/queue/{name}", tags=["Queues"])
def list_queue(name: str, limit: int = Query(default=50, ge=1, le=500)):
    """
    List tasks in a named queue.

    `name` must be one of:
    needs_action | waiting_approval | pending_approval | approved | done | retry_queue
    """
    q_path = _queue_path(name)
    if not q_path.exists():
        return {"queue": name, "count": 0, "tasks": []}

    tasks = []
    for f in sorted(q_path.iterdir()):
        if not f.is_file():
            continue
        if len(tasks) >= limit:
            break
        entry: dict[str, Any] = {"filename": f.name, "size_bytes": f.stat().st_size}
        if f.suffix == ".json":
            data = _parse_task(f)
            # Surface useful top-level fields without dumping the full payload
            for field in ("id", "task_type", "action", "timestamp", "status", "result"):
                if field in data:
                    entry[field] = data[field]
        tasks.append(entry)

    return {"queue": name, "count": len(tasks), "tasks": tasks}


@app.get("/task/{queue}/{filename}", tags=["Queues"])
def get_task(queue: str, filename: str):
    """Return the full JSON content of a specific task file."""
    filename = _safe_filename(filename)
    q_path   = _queue_path(queue)
    task_path = q_path / filename

    if not task_path.exists():
        raise HTTPException(status_code=404, detail=f"Task '{filename}' not found in {queue}.")

    if task_path.suffix == ".json":
        return _parse_task(task_path)

    # Markdown / plain-text files
    return {"filename": filename, "content": task_path.read_text(encoding="utf-8")}


@app.get("/logs/execution", tags=["Logs"])
def logs_execution(tail: int = Query(default=50, ge=1, le=500)):
    """Tail the execution log (LOG_DIR/execution_log.json)."""
    entries = _tail_jsonl(LOG_DIR / "execution_log.json", tail)
    return {"count": len(entries), "entries": entries}


@app.get("/logs/health", tags=["Logs"])
def logs_health(tail: int = Query(default=50, ge=1, le=500)):
    """Tail the health log (LOG_DIR/health_log.json)."""
    entries = _tail_jsonl(LOG_DIR / "health_log.json", tail)
    return {"count": len(entries), "entries": entries}


@app.get("/logs/prompt", tags=["Logs"])
def logs_prompt(tail: int = Query(default=20, ge=1, le=200)):
    """Tail the SHA-256-chained prompt log (LOG_DIR/prompt_chain.json)."""
    entries = _tail_jsonl(LOG_DIR / "prompt_chain.json", tail)
    return {"count": len(entries), "entries": entries}


@app.get("/evidence/judge-proof", tags=["Evidence"])
def evidence_judge_proof():
    """Return the content of Evidence/JUDGE_PROOF.md as plain text."""
    path = EVIDENCE_DIR / "JUDGE_PROOF.md"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="JUDGE_PROOF.md not found. Run: python scripts/generate_evidence_pack.py --n 20",
        )
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.get("/evidence/list", tags=["Evidence"])
def evidence_list():
    """List all files in the Evidence/ directory."""
    if not EVIDENCE_DIR.exists():
        return {"count": 0, "files": []}
    files = []
    for f in sorted(EVIDENCE_DIR.iterdir()):
        if f.is_file():
            files.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "suffix": f.suffix,
            })
    return {"count": len(files), "files": files}


# ── HITL Endpoints ────────────────────────────────────────────────────────────

def _hitl_source_path(filename: str) -> Path:
    """
    Resolve the source path for an approval action.
    Prefers vault/Waiting_Approval if it exists, otherwise vault/Pending_Approval.
    """
    wa = QUEUE_DIRS["waiting_approval"]
    pa = QUEUE_DIRS["pending_approval"]
    candidate_wa = wa / filename
    candidate_pa = pa / filename

    if candidate_wa.exists():
        return candidate_wa
    if candidate_pa.exists():
        return candidate_pa
    raise HTTPException(
        status_code=404,
        detail=f"Task '{filename}' not found in Waiting_Approval or Pending_Approval.",
    )


@app.post("/approve/{filename}", tags=["HITL"])
def approve_task(filename: str):
    """
    HITL Approval endpoint.

    Moves the task from vault/Waiting_Approval (or vault/Pending_Approval)
    → vault/Pending_Approval (ready for Local Executor pickup).

    If the file is already in Pending_Approval, marks approved in the log
    and returns without moving.
    """
    filename = _safe_filename(filename)
    source   = _hitl_source_path(filename)
    dest_dir = QUEUE_DIRS["pending_approval"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename

    # If already in Pending_Approval, nothing to move
    if source == dest:
        _append_approval_log(filename, action="already_pending")
        return {"status": "ok", "action": "already_pending", "filename": filename}

    if dest.exists():
        raise HTTPException(
            status_code=409,
            detail=f"A file named '{filename}' already exists in Pending_Approval.",
        )

    source.rename(dest)
    _append_approval_log(filename, action="approved")
    return {
        "status":   "ok",
        "action":   "approved",
        "filename": filename,
        "moved_to": str(dest),
    }


@app.post("/reject/{filename}", tags=["HITL"])
def reject_task(filename: str):
    """
    HITL Rejection endpoint.

    Moves the task from vault/Waiting_Approval (or vault/Pending_Approval)
    → vault/Rejected/.
    """
    filename = _safe_filename(filename)
    source   = _hitl_source_path(filename)
    dest_dir = VAULT_DIR / "Rejected"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename

    if dest.exists():
        raise HTTPException(
            status_code=409,
            detail=f"A file named '{filename}' already exists in Rejected.",
        )

    source.rename(dest)
    _append_approval_log(filename, action="rejected")
    return {
        "status":   "ok",
        "action":   "rejected",
        "filename": filename,
        "moved_to": str(dest),
    }


def _append_approval_log(filename: str, action: str) -> None:
    """Append an approval/rejection event to LOG_DIR/execution_log.json."""
    log_path = LOG_DIR / "execution_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = json.dumps({
        "id":        filename,
        "task_type": "hitl_decision",
        "action":    action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    "backend_api",
    })
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(record + "\n")


# ── Actions ───────────────────────────────────────────────────────────────────

@app.post("/evidence/generate", tags=["Actions"])
def generate_evidence(n: int = Query(default=20, ge=1, le=200)):
    """
    Trigger evidence pack generation by calling
    scripts/generate_evidence_pack.py --n <n>.

    Returns the path to the generated file and a short snippet.
    """
    script = SCRIPTS_DIR / "generate_evidence_pack.py"
    if not script.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Evidence script not found at {script}",
        )

    try:
        result = subprocess.run(
            [sys.executable, str(script), "--n", str(n)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(VAULT_ROOT),
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Evidence generation timed out.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Script execution error: {exc}")

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Script exited {result.returncode}: {result.stderr[:400]}",
        )

    out_path = EVIDENCE_DIR / "JUDGE_PROOF.md"
    snippet  = ""
    if out_path.exists():
        lines   = out_path.read_text(encoding="utf-8").splitlines()
        snippet = "\n".join(lines[:15])

    return {
        "status":   "ok",
        "path":     str(out_path),
        "exists":   out_path.exists(),
        "snippet":  snippet,
        "stdout":   result.stdout[:500],
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
