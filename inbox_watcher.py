"""
inbox_watcher.py — Gold Tier Inbox Watcher (BaseWatcher subclass).

Watches Inbox/ for *.md task files and moves them to Needs_Action/ with
standardized YAML frontmatter injected when the file has none.

Frontmatter fields added (only when missing):
  source:       inbox
  ingested_at:  UTC ISO 8601 timestamp
  watcher:      inbox_watcher
  status:       pending

This watcher is cloud-safe:
  --once flag  -> one scan then exit (GitHub Actions / scheduled cron)
  (no flag)    -> infinite polling loop (local development)

Usage:
  python inbox_watcher.py                  # local dev — infinite loop, 5s poll
  python inbox_watcher.py --once           # GitHub Actions — one scan, then exit
  python inbox_watcher.py --interval 30    # local dev — 30s poll interval
  python inbox_watcher.py --once --dir /custom/vault
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from audit_logger import log_action
from base_watcher import BaseWatcher

SERVER_NAME = "inbox_watcher"
BASE_DIR = Path(__file__).resolve().parent


class InboxWatcher(BaseWatcher):
    """
    Concrete watcher: Inbox/ -> Needs_Action/.

    On each run_once() call:
      1. Glob Inbox/*.md (skip .gitkeep)
      2. If file has no YAML frontmatter -> inject standardised fields
      3. Write enriched content to Needs_Action/<filename>
      4. Delete source file from Inbox/
      5. Log the ingest event to audit_logger
    """

    name: ClassVar[str] = SERVER_NAME

    def __init__(
        self,
        base_dir: Path,
        poll_interval: float = 5.0,
        one_shot: bool = False,
    ) -> None:
        super().__init__(base_dir=base_dir, poll_interval=poll_interval, one_shot=one_shot)
        self.inbox = base_dir / "Inbox"
        self.needs_action = base_dir / "Needs_Action"

    # ── BaseWatcher implementation ────────────────────────────────────────────

    def run_once(self) -> int:
        """
        One scan: ingest all *.md files from Inbox/ into Needs_Action/.
        Returns count of files successfully ingested.
        """
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.needs_action.mkdir(parents=True, exist_ok=True)

        candidates = sorted(
            f for f in self.inbox.glob("*.md")
            if f.name != ".gitkeep"
        )

        processed = 0
        for src in candidates:
            dst = self.needs_action / src.name
            try:
                raw = src.read_text(encoding="utf-8")
                had_frontmatter = _has_yaml_frontmatter(raw)
                standardized = raw if had_frontmatter else _inject_frontmatter(raw)

                dst.write_text(standardized, encoding="utf-8")
                src.unlink()

                log_action(SERVER_NAME, "task_ingested", {
                    "filename": src.name,
                    "had_frontmatter": had_frontmatter,
                    "destination": "Needs_Action/",
                })
                suffix = "  (frontmatter added)" if not had_frontmatter else ""
                print(f"  [{SERVER_NAME}] {src.name} -> Needs_Action/{suffix}")
                processed += 1

            except Exception as exc:
                log_action(SERVER_NAME, "ingest_error", {
                    "filename": src.name,
                    "error": str(exc),
                }, success=False)
                print(f"  [{SERVER_NAME}] ERROR ingesting {src.name}: {exc}")

        return processed


# ── Pure helpers (module-level, no side effects) ──────────────────────────────

def _has_yaml_frontmatter(content: str) -> bool:
    """Return True if content begins with a YAML --- block."""
    return content.lstrip().startswith("---")


def _inject_frontmatter(content: str) -> str:
    """
    Prepend standardised YAML frontmatter to a task file.

    Does NOT alter existing content — only prepends the block.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    frontmatter = (
        "---\n"
        "source: inbox\n"
        f'ingested_at: "{now_iso}"\n'
        "watcher: inbox_watcher\n"
        "status: pending\n"
        "---\n\n"
    )
    return frontmatter + content


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    watcher = InboxWatcher.cli(base_dir=BASE_DIR, default_interval=5.0)
    watcher.run()
