"""
tools/mcp_health_report.py
--------------------------
MCP Health Report — Gold Tier Diagnostic Tool

Outputs:
  - Registered MCP tools (from Evidence/REGISTERED_MCP_TOOLS.json)
  - MCP_DRY_RUN environment value
  - Last log timestamp (from Logs/*.json)
  - Writes Evidence/MCP_HEALTH_REPORT.json
"""

from __future__ import annotations

import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 output on Windows terminals that default to cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
elif sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / "Evidence"
LOGS_DIR = BASE_DIR / "Logs"
REGISTERED_TOOLS_FILE = EVIDENCE_DIR / "REGISTERED_MCP_TOOLS.json"
OUTPUT_FILE = EVIDENCE_DIR / "MCP_HEALTH_REPORT.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_registered_tools() -> dict:
    """Load tool registry from Evidence/REGISTERED_MCP_TOOLS.json."""
    if not REGISTERED_TOOLS_FILE.exists():
        return {"error": "REGISTERED_MCP_TOOLS.json not found — run generate_evidence_pack.py first"}
    try:
        return json.loads(REGISTERED_TOOLS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _get_dry_run_value() -> str:
    """Return MCP_DRY_RUN env value, or 'true' (safe default if unset)."""
    raw = os.environ.get("MCP_DRY_RUN")
    if raw is None:
        return "true (default — not explicitly set)"
    return raw.strip().lower()


def _get_last_log_timestamp() -> str | None:
    """Return ISO timestamp of the most-recently-written Logs/*.json entry."""
    if not LOGS_DIR.is_dir():
        return None

    latest_ts: str | None = None
    latest_mtime: float = 0.0

    for log_file in LOGS_DIR.glob("*.json"):
        mtime = log_file.stat().st_mtime
        if mtime > latest_mtime:
            latest_mtime = mtime
            # Try to read the timestamp field from the JSON itself
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "timestamp" in data:
                    latest_ts = data["timestamp"]
                elif isinstance(data, list) and data and "timestamp" in data[-1]:
                    latest_ts = data[-1]["timestamp"]
                else:
                    # Fall back to file mtime
                    latest_ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            except Exception:
                latest_ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    return latest_ts


def _count_logs_by_server() -> dict[str, int]:
    """Tally how many log entries exist per MCP server."""
    counts: dict[str, int] = {}
    if not LOGS_DIR.is_dir():
        return counts
    for log_file in LOGS_DIR.glob("*.json"):
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                server = entry.get("server", "unknown")
                counts[server] = counts.get(server, 0) + 1
        except Exception:
            pass
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


# ── main ──────────────────────────────────────────────────────────────────────

def run() -> dict:
    EVIDENCE_DIR.mkdir(exist_ok=True)

    registry = _load_registered_tools()
    dry_run = _get_dry_run_value()
    last_log_ts = _get_last_log_timestamp()
    server_counts = _count_logs_by_server()
    total_logs = sum(server_counts.values())

    tools_dict: dict = registry.get("tools", {})
    tool_count: int = registry.get("tool_count", len(tools_dict))

    # Group tools by server
    by_server: dict[str, list[str]] = {}
    for tool_name, server in tools_dict.items():
        by_server.setdefault(server, []).append(tool_name)

    report = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mcp_dry_run": dry_run,
        "registered_tools": {
            "total": tool_count,
            "tools": tools_dict,
            "by_server": by_server,
        },
        "last_log_timestamp": last_log_ts or "no logs found",
        "log_stats": {
            "total_log_entries": total_logs,
            "entries_by_server": server_counts,
        },
        "health_status": "OK" if not registry.get("error") else "DEGRADED",
        "source": {
            "registry_file": str(REGISTERED_TOOLS_FILE.relative_to(BASE_DIR)),
            "logs_dir": str(LOGS_DIR.relative_to(BASE_DIR)),
        },
    }

    OUTPUT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _print_report(report: dict) -> None:
    w = 62
    print("=" * w)
    print("  MCP Health Report — AI Employee Vault Gold Tier")
    print("=" * w)
    print(f"  Generated     : {report['generated']}")
    print(f"  Health Status : {report['health_status']}")
    print(f"  MCP_DRY_RUN   : {report['mcp_dry_run']}")
    print(f"  Last Log TS   : {report['last_log_timestamp']}")
    print()

    rt = report["registered_tools"]
    print(f"  Registered Tools ({rt['total']}):")
    for server, tools in sorted(rt["by_server"].items()):
        print(f"    [{server}]")
        for t in sorted(tools):
            print(f"      - {t}")
    print()

    ls = report["log_stats"]
    print(f"  Log Entries : {ls['total_log_entries']} total")
    print("  By Server   :")
    for server, count in ls["entries_by_server"].items():
        bar = "#" * min(count // 10, 30)
        print(f"    {server:<28} {count:>5}  {bar}")
    print()
    print(f"  Report saved → Evidence/MCP_HEALTH_REPORT.json")
    print("=" * w)


if __name__ == "__main__":
    report = run()
    _print_report(report)
    sys.exit(0 if report["health_status"] == "OK" else 1)
