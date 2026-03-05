"""
AI Employee Vault – Platinum Tier
Self-Monitoring System  |  monitoring/health_monitor.py

Monitors:
  - Cloud Agent (agent_heartbeat.json — threshold 30 s)
  - Gmail Watcher (gmail_watcher_heartbeat.json — threshold 60 s)
  - Local Executor (local_executor_heartbeat.json — threshold 30 s)
  - MCP tool stubs (import checks)

On anomaly:
  - Logs to Evidence/SYSTEM_HEALTH_REPORT.md
  - Can trigger watchdog restart commands (optional)

Usage:
    python -m monitoring.health_monitor              # continuous (15 s interval)
    python -m monitoring.health_monitor --once       # single check
    python -m monitoring.health_monitor --interval 30
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Path helpers ───────────────────────────────────────────────────────────────

def _vault_dir() -> Path:
    return Path(os.getenv("VAULT_DIR", str(Path(__file__).resolve().parent.parent / "vault")))

def _evidence_dir() -> Path:
    return Path(os.getenv("EVIDENCE_OUT_DIR", str(Path(__file__).resolve().parent.parent / "Evidence")))

def _log_dir() -> Path:
    return Path(os.getenv("VAULT_LOG_DIR", str(_vault_dir() / "Logs")))


# ── Component specs ────────────────────────────────────────────────────────────

COMPONENTS = {
    "cloud_agent": {
        "heartbeat_file": "agent_heartbeat.json",
        "threshold_s":    30.0,
        "restart_cmd":    ["python", "cloud_agent.py", "--daemon", "--auto", "--interval", "5"],
    },
    "gmail_watcher": {
        "heartbeat_file": "gmail_watcher_heartbeat.json",
        "threshold_s":    60.0,
        "restart_cmd":    ["python", "-m", "watchers.gmail_watcher", "--daemon", "--interval", "30"],
    },
    "local_executor": {
        "heartbeat_file": "local_executor_heartbeat.json",
        "threshold_s":    30.0,
        "restart_cmd":    ["python", "local_executor.py", "--poll", "2"],
    },
}

MCP_MODULES = [
    "mcp_email_ops",
    "mcp_calendar_ops",
    "mcp_file_ops",
    "mcp_social_facebook",
]


# ── Component health check ─────────────────────────────────────────────────────

def _check_component(name: str, spec: dict) -> dict[str, Any]:
    hb_path = _log_dir() / spec["heartbeat_file"]
    now = datetime.now(timezone.utc)

    if not hb_path.exists():
        return {"name": name, "status": "offline", "reason": "heartbeat file missing",
                "last_seen": None, "age_s": None}

    try:
        data = json.loads(hb_path.read_text(encoding="utf-8"))
        ts_str = data.get("timestamp")
        if not ts_str:
            return {"name": name, "status": "offline", "reason": "no timestamp in heartbeat",
                    "last_seen": None, "age_s": None}

        ts  = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        age = (now - ts).total_seconds()

        if age <= spec["threshold_s"]:
            return {"name": name, "status": "online", "reason": "heartbeat fresh",
                    "last_seen": ts_str, "age_s": round(age, 1)}
        else:
            return {"name": name, "status": "degraded", "reason": f"heartbeat stale ({age:.0f}s old)",
                    "last_seen": ts_str, "age_s": round(age, 1)}

    except Exception as exc:
        return {"name": name, "status": "offline", "reason": f"heartbeat parse error: {exc}",
                "last_seen": None, "age_s": None}


def _check_mcp_tools() -> dict[str, Any]:
    """Verify MCP tool modules are importable."""
    results: dict[str, str] = {}
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    for mod in MCP_MODULES:
        try:
            __import__(mod)
            results[mod] = "ok"
        except ImportError:
            results[mod] = "import_error"
        except Exception as exc:
            results[mod] = f"error: {exc}"
    return {"mcp_tools": results}


# ── Evidence writer ────────────────────────────────────────────────────────────

def _write_report(check_results: list[dict], mcp_status: dict, cycle: int) -> None:
    ev_dir = _evidence_dir()
    ev_dir.mkdir(parents=True, exist_ok=True)
    report_path = ev_dir / "SYSTEM_HEALTH_REPORT.md"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_rows = "\n".join(
        f"| {r['name']} | `{r['status']}` | {r.get('age_s', 'N/A')}s | {r['reason']} |"
        for r in check_results
    )
    mcp_rows = "\n".join(
        f"| {mod} | `{status}` |"
        for mod, status in mcp_status.get("mcp_tools", {}).items()
    )
    all_ok = all(r["status"] == "online" for r in check_results)
    summary = "✅ ALL SYSTEMS ONLINE" if all_ok else "⚠️ DEGRADED — see below"

    block = (
        f"\n## Health Check — Cycle {cycle} — {ts}\n\n"
        f"**Status:** {summary}\n\n"
        f"### Process Health\n\n"
        f"| Component | Status | Heartbeat Age | Reason |\n|---|---|---|---|\n"
        f"{status_rows}\n\n"
        f"### MCP Tools\n\n"
        f"| Module | Status |\n|---|---|\n"
        f"{mcp_rows}\n\n"
        f"---\n"
    )

    try:
        with open(report_path, "a", encoding="utf-8") as fh:
            fh.write(block)
    except OSError as exc:
        log.warning("[monitor] report write failed: %s", exc)


def _ensure_header() -> None:
    ev_dir = _evidence_dir()
    ev_dir.mkdir(parents=True, exist_ok=True)
    path = ev_dir / "SYSTEM_HEALTH_REPORT.md"
    if not path.exists() or path.stat().st_size == 0:
        path.write_text(
            "# System Health Report\n\n"
            "Append-only monitoring log for AI Employee Vault – Platinum Tier.\n\n"
            "Components monitored: cloud_agent · gmail_watcher · local_executor · MCP tools\n\n",
            encoding="utf-8",
        )


# ── Single check ───────────────────────────────────────────────────────────────

_cycle = 0

def run_check(print_summary: bool = True) -> list[dict]:
    global _cycle
    _cycle += 1

    results = [_check_component(name, spec) for name, spec in COMPONENTS.items()]
    mcp_status = _check_mcp_tools()

    _write_report(results, mcp_status, _cycle)

    if print_summary:
        for r in results:
            icon = {"online": "✅", "degraded": "⚠️", "offline": "❌"}.get(r["status"], "?")
            print(f"  {icon} {r['name']:<20} {r['status']:<10}  {r['reason']}")

    # Log anomalies
    for r in results:
        if r["status"] != "online":
            log.warning("[monitor] %s is %s — %s", r["name"], r["status"], r["reason"])

    return results


# ── Main loop ──────────────────────────────────────────────────────────────────

def run_loop(interval: float = 15.0) -> None:
    _ensure_header()
    log.info("[monitor] health monitor started (interval=%.0fs)", interval)
    while True:
        try:
            run_check()
        except Exception as exc:
            log.warning("[monitor] check error: %s", exc)
        time.sleep(interval)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-8s %(message)s")
    parser = argparse.ArgumentParser(description="AI Vault Health Monitor")
    parser.add_argument("--once",     action="store_true", help="Run one check and exit")
    parser.add_argument("--interval", type=float, default=15.0, help="Check interval seconds")
    args = parser.parse_args()

    _ensure_header()
    if args.once:
        results = run_check()
        ok = all(r["status"] == "online" for r in results)
        sys.exit(0 if ok else 1)
    else:
        run_loop(interval=args.interval)
