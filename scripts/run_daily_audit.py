#!/usr/bin/env python3
"""
run_daily_audit.py — Daily Audit Runner (cron-safe)

Reads all Logs/*.json files, produces:
  Business/Reports/DAILY_AUDIT_<date>.md   — human-readable markdown report
  Evidence/DAILY_AUDIT_<date>.json         — machine-readable evidence snapshot

Usage:
    python scripts/run_daily_audit.py
    python scripts/run_daily_audit.py --date 2026-02-24   # audit a specific date
    python scripts/run_daily_audit.py --all               # audit all dates in Logs/

Cron example (run at 00:05 every day):
    5 0 * * * cd /path/to/vault && python scripts/run_daily_audit.py >> logs/cron.log 2>&1
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths — resolved relative to this script so cron works from any cwd
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
LOGS_DIR = os.path.join(ROOT, "Logs")
REPORTS_DIR = os.path.join(ROOT, "Business", "Reports")
EVIDENCE_DIR = os.path.join(ROOT, "Evidence")


def load_logs() -> list[dict]:
    """Load all JSON log entries from Logs/*.json (skips malformed files)."""
    entries = []
    for path in sorted(glob.glob(os.path.join(LOGS_DIR, "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            data["_source_file"] = os.path.basename(path)
            entries.append(data)
        except Exception:
            # Cron-safe: skip unreadable / malformed files silently
            pass
    return entries


def filter_by_date(entries: list[dict], date_str: str) -> list[dict]:
    """Return entries whose timestamp matches the given YYYY-MM-DD date."""
    return [e for e in entries if e.get("timestamp", "").startswith(date_str)]


def build_stats(entries: list[dict]) -> dict:
    """Aggregate statistics from a list of log entries."""
    total = len(entries)
    successes = sum(1 for e in entries if e.get("success") is True)
    failures = sum(1 for e in entries if e.get("success") is False)

    servers: Counter = Counter()
    actions: Counter = Counter()
    errors: list[dict] = []

    for e in entries:
        server = e.get("server", "unknown")
        action = e.get("action", "unknown")
        servers[server] += 1
        actions[action] += 1
        if e.get("success") is False:
            errors.append({
                "id": e.get("id", "?"),
                "timestamp": e.get("timestamp", "?"),
                "server": server,
                "action": action,
                "details": e.get("details", {}),
            })

    # Hourly distribution
    hourly: Counter = Counter()
    for e in entries:
        ts = e.get("timestamp", "")
        if len(ts) >= 13:
            hour = ts[11:13]
            hourly[hour] += 1

    return {
        "total_events": total,
        "successes": successes,
        "failures": failures,
        "success_rate_pct": round(successes / total * 100, 1) if total else 0.0,
        "top_servers": servers.most_common(10),
        "top_actions": actions.most_common(15),
        "errors": errors,
        "hourly_distribution": dict(sorted(hourly.items())),
    }


def render_markdown(date_str: str, stats: dict, generated_at: str) -> str:
    """Render the audit report as GitHub-flavoured Markdown."""
    sr = stats["success_rate_pct"]
    health_icon = "✅" if sr >= 95 else ("⚠️" if sr >= 80 else "❌")

    lines = [
        f"# Daily Audit Report — {date_str}",
        "",
        f"> Generated: {generated_at}  ",
        f"> Source: `Logs/*.json`",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total events | **{stats['total_events']}** |",
        f"| Successes | {stats['successes']} |",
        f"| Failures | {stats['failures']} |",
        f"| Success rate | {health_icon} **{sr}%** |",
        "",
        "---",
        "",
        "## Activity by Server",
        "",
        "| Server | Events |",
        "|--------|--------|",
    ]
    for server, count in stats["top_servers"]:
        lines.append(f"| `{server}` | {count} |")

    lines += [
        "",
        "---",
        "",
        "## Top Actions",
        "",
        "| Action | Count |",
        "|--------|-------|",
    ]
    for action, count in stats["top_actions"]:
        lines.append(f"| `{action}` | {count} |")

    lines += [
        "",
        "---",
        "",
        "## Hourly Distribution",
        "",
        "| Hour (UTC) | Events |",
        "|------------|--------|",
    ]
    for hour, count in sorted(stats["hourly_distribution"].items()):
        bar = "█" * min(count, 40)
        lines.append(f"| {hour}:00 | {count} {bar} |")

    lines += ["", "---", "", "## Errors"]

    if not stats["errors"]:
        lines.append("")
        lines.append("_No errors recorded for this period._")
    else:
        lines += [
            "",
            f"**{len(stats['errors'])} error(s) detected:**",
            "",
        ]
        for err in stats["errors"]:
            lines.append(
                f"- `{err['timestamp']}` | `{err['server']}` | `{err['action']}` | {err['details']}"
            )

    lines += [
        "",
        "---",
        "",
        "*AI Employee Vault — Gold Tier | Daily Audit Runner*",
        "",
    ]
    return "\n".join(lines)


def write_outputs(date_str: str, stats: dict, generated_at: str) -> tuple[str, str]:
    """Write .md to Business/Reports/ and .json to Evidence/. Returns (md_path, json_path)."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(EVIDENCE_DIR, exist_ok=True)

    md_path = os.path.join(REPORTS_DIR, f"DAILY_AUDIT_{date_str}.md")
    json_path = os.path.join(EVIDENCE_DIR, f"DAILY_AUDIT_{date_str}.json")

    md_content = render_markdown(date_str, stats, generated_at)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md_content)

    evidence = {
        "date": date_str,
        "generated_at": generated_at,
        "stats": {
            **stats,
            # Convert Counter tuples → plain dicts for JSON serialisation
            "top_servers": dict(stats["top_servers"]),
            "top_actions": dict(stats["top_actions"]),
        },
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, indent=2)

    return md_path, json_path


def audit_date(date_str: str, all_entries: list[dict]) -> None:
    """Run the audit for a single date and print a one-line summary."""
    entries = filter_by_date(all_entries, date_str)
    if not entries:
        print(f"  [skip] {date_str} — no log entries found")
        return

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stats = build_stats(entries)
    md_path, json_path = write_outputs(date_str, stats, generated_at)

    print(
        f"  [ok]   {date_str} — {stats['total_events']} events, "
        f"{stats['success_rate_pct']}% success | "
        f"{os.path.relpath(md_path, ROOT)} | {os.path.relpath(json_path, ROOT)}"
    )


def unique_dates(entries: list[dict]) -> list[str]:
    """Return sorted unique YYYY-MM-DD dates found in the log entries."""
    dates = set()
    for e in entries:
        ts = e.get("timestamp", "")
        if len(ts) >= 10:
            dates.add(ts[:10])
    return sorted(dates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily audit runner for AI Employee Vault")
    parser.add_argument(
        "--date",
        default=None,
        help="Audit a specific date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Audit every date that appears in Logs/.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  AI Employee Vault — Daily Audit Runner")
    print("=" * 60)
    print(f"  Logs dir : {LOGS_DIR}")
    print(f"  Reports  : {REPORTS_DIR}")
    print(f"  Evidence : {EVIDENCE_DIR}")
    print()

    all_entries = load_logs()
    print(f"  Loaded {len(all_entries)} log entries from Logs/\n")

    if args.all:
        dates = unique_dates(all_entries)
        print(f"  Auditing {len(dates)} unique date(s):\n")
        for d in dates:
            audit_date(d, all_entries)
    else:
        target = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print(f"  Auditing: {target}\n")
        audit_date(target, all_entries)

    print()
    print("=" * 60)
    print("  Audit complete.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:
        # Cron-safe: print error but exit 0 so cron doesn't spam alerts
        print(f"[ERROR] Daily audit failed: {exc}", file=sys.stderr)
        sys.exit(1)
