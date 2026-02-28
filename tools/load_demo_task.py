#!/usr/bin/env python3
"""
tools/load_demo_task.py — Copy a demo scenario into Inbox/ with a timestamped filename.

Usage
-----
    python tools/load_demo_task.py --list
    python tools/load_demo_task.py facebook_post_demo
    python tools/load_demo_task.py instagram_post_demo
    python tools/load_demo_task.py twitter_post_demo
    python tools/load_demo_task.py odoo
    python tools/load_demo_task.py gmail
    python tools/load_demo_task.py browser

Timestamped filenames prevent collisions when running multiple demos in sequence.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_DIR = BASE_DIR / "Demo_Scenarios"
INBOX_DIR = BASE_DIR / "Inbox"

# ── Scenario aliases ──────────────────────────────────────────────────────────
_ALIASES: dict[str, str] = {
    # Social media demos
    "facebook_post_demo":  "facebook_post_demo.md",
    "facebook":            "facebook_post_demo.md",
    "fb":                  "facebook_post_demo.md",
    "instagram_post_demo": "instagram_post_demo.md",
    "instagram":           "instagram_post_demo.md",
    "ig":                  "instagram_post_demo.md",
    "twitter_post_demo":   "twitter_post_demo.md",
    "twitter":             "twitter_post_demo.md",
    "tw":                  "twitter_post_demo.md",
    # Legacy aliases (from earlier demos)
    "odoo":    "odoo_demo.md",
    "gmail":   "gmail_demo.md",
    "browser": "browser_demo.md",
}


def _list_scenarios() -> None:
    """Print available demo scenarios."""
    files = sorted(DEMO_DIR.glob("*.md"))
    if not files:
        print(f"No demo scenarios found in {DEMO_DIR}/")
        return

    print(f"Available demo scenarios in {DEMO_DIR.name}/:")
    for f in files:
        alias_keys = [k for k, v in _ALIASES.items() if v == f.name]
        aliases = f"  (aliases: {', '.join(alias_keys)})" if alias_keys else ""
        print(f"  {f.name}{aliases}")

    print()
    print("Usage:")
    print("  python tools/load_demo_task.py facebook_post_demo")
    print("  python tools/load_demo_task.py instagram")
    print("  python tools/load_demo_task.py tw")


def _load_scenario(name: str) -> int:
    """
    Copy the named scenario into Inbox/ with a timestamped prefix.

    Returns 0 on success, 1 on failure.
    """
    # Resolve alias or direct filename
    filename = _ALIASES.get(name.lower(), name)
    if not filename.endswith(".md"):
        filename += ".md"

    src = DEMO_DIR / filename
    if not src.exists():
        print(f"ERROR: Demo scenario not found: {src}")
        print(f"Run 'python tools/load_demo_task.py --list' to see available scenarios.")
        return 1

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest_name = f"demo_{ts}_{filename}"
    dest = INBOX_DIR / dest_name

    shutil.copy2(src, dest)
    print(f"Loaded demo scenario into Inbox/")
    print(f"  Source:      Demo_Scenarios/{filename}")
    print(f"  Destination: Inbox/{dest_name}")
    print()
    print("Next steps:")
    print("  1. python gold_agent.py          # run the agent")
    print("  2. python approve.py --all       # approve pending HITL actions")
    print("  3. python gold_agent.py          # agent resumes and fires MCP tool")
    print("  4. ls Logs/                      # confirm audit log written")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load a demo scenario into Inbox/ for the Gold Agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        help="Scenario name or alias (e.g. facebook_post_demo, instagram, tw)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available demo scenarios and exit",
    )
    args = parser.parse_args()

    if args.list or args.scenario is None:
        _list_scenarios()
        return 0

    return _load_scenario(args.scenario)


if __name__ == "__main__":
    sys.exit(main())
