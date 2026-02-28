"""
base_watcher.py — Abstract BaseWatcher for Gold Tier.

Provides a clean, reusable watcher skeleton:
  - Abstract interface: subclasses implement run_once() -> int
  - Run loop: infinite (local dev) or one-shot (GitHub Actions / cron)
  - Exponential backoff on consecutive errors (doubles per error, capped at 60s)
  - Structured audit logging via audit_logger on every event
  - Standardised CLI: --once, --interval, --dir

How to subclass:

    from base_watcher import BaseWatcher

    class MyWatcher(BaseWatcher):
        name = "my_watcher"

        def run_once(self) -> int:
            # do your thing, return count of items processed
            return 0

    if __name__ == "__main__":
        watcher = MyWatcher.cli(base_dir=BASE_DIR, default_interval=10.0)
        watcher.run()
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from audit_logger import log_action


class BaseWatcher(ABC):
    """
    Abstract base class for all Gold Tier watchers.

    Subclasses MUST define:
      name (ClassVar[str])  — identifier used in logs and console output
      run_once() -> int     — one scan cycle; return count of items processed

    The base class provides the full run loop, error handling + backoff, and CLI.
    Subclasses should not need to override run() or cli().
    """

    name: ClassVar[str] = "base_watcher"

    # ── Backoff config ────────────────────────────────────────────────────────
    _MAX_BACKOFF: ClassVar[float] = 60.0   # max sleep on repeated errors (seconds)
    _BACKOFF_FACTOR: ClassVar[float] = 2.0  # multiplier per consecutive error

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(
        self,
        base_dir: Path,
        poll_interval: float = 5.0,
        one_shot: bool = False,
    ) -> None:
        """
        Args:
            base_dir:      Vault root directory.
            poll_interval: Seconds between scan cycles (ignored when one_shot=True).
            one_shot:      If True, call run_once() once then exit cleanly.
                           Set this flag when running inside GitHub Actions / cron.
        """
        self.base_dir = base_dir
        self.poll_interval = poll_interval
        self.one_shot = one_shot
        self._consecutive_errors: int = 0

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def run_once(self) -> int:
        """
        Perform one scan cycle.

        Returns:
            Number of items processed (logged when > 0).

        Implementations MUST catch their own exceptions and return 0 on error.
        Unhandled exceptions are caught by the run loop, which applies backoff.
        """
        ...

    # ── Run loop ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Main entry point. Call this from __main__ (or from your CLI entry point).

        Mode determined by self.one_shot:
          one_shot=True   -> call run_once() once, then exit  (GitHub Actions mode)
          one_shot=False  -> loop forever, sleeping poll_interval between cycles
                            until KeyboardInterrupt               (local dev mode)
        """
        mode = "one-shot" if self.one_shot else f"polling every {self.poll_interval}s"
        print(f"[{self.name}] Starting ({mode})")
        log_action(self.name, "watcher_start", {
            "mode": mode,
            "base_dir": str(self.base_dir),
            "one_shot": self.one_shot,
            "poll_interval": self.poll_interval,
        })

        iterations = 0
        try:
            while True:
                iterations += 1
                ts = datetime.now(timezone.utc).strftime("%H:%M:%SZ")

                try:
                    count = self.run_once()
                    self._consecutive_errors = 0
                    if count > 0:
                        print(f"[{self.name}] {ts} — {count} item(s) processed")
                        log_action(self.name, "scan_processed", {
                            "count": count,
                            "iteration": iterations,
                        })

                except Exception as exc:
                    self._consecutive_errors += 1
                    backoff = self._backoff_delay()
                    backoff_note = f" — backoff {backoff:.0f}s" if backoff else ""
                    print(
                        f"[{self.name}] {ts} ERROR "
                        f"#{self._consecutive_errors}: {exc}{backoff_note}"
                    )
                    log_action(self.name, "scan_error", {
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "consecutive_errors": self._consecutive_errors,
                        "backoff_s": backoff,
                        "iteration": iterations,
                    }, success=False)
                    if backoff:
                        time.sleep(backoff)

                if self.one_shot:
                    break

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print(f"\n[{self.name}] Interrupted by user.")

        log_action(self.name, "watcher_stop", {
            "iterations": iterations,
            "one_shot": self.one_shot,
        })
        print(f"[{self.name}] Stopped. Total iterations: {iterations}")

    # ── CLI factory ───────────────────────────────────────────────────────────

    @classmethod
    def cli(
        cls,
        base_dir: Path | None = None,
        default_interval: float = 5.0,
    ) -> "BaseWatcher":
        """
        Parse CLI arguments and return a configured watcher instance.

        Flags recognised:
          --once           Run one scan cycle then exit (GitHub Actions / cron).
          --interval N     Poll interval in seconds for continuous mode.
          --dir PATH       Override vault base directory.

        Usage in subclass __main__:
            watcher = MyWatcher.cli(base_dir=BASE_DIR, default_interval=10.0)
            watcher.run()
        """
        parser = ArgumentParser(
            prog=cls.name,
            description=f"{cls.name} — Gold Tier watcher",
            formatter_class=RawDescriptionHelpFormatter,
            epilog=(
                "Examples:\n"
                f"  python {cls.name}.py                   # local dev (infinite loop)\n"
                f"  python {cls.name}.py --once            # GitHub Actions / cron\n"
                f"  python {cls.name}.py --interval 30     # poll every 30s\n"
                f"  python {cls.name}.py --once --dir /custom/vault\n"
            ),
        )
        parser.add_argument(
            "--once",
            action="store_true",
            default=False,
            help="Run one scan cycle then exit cleanly (use in GitHub Actions / cron)",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=default_interval,
            metavar="SECONDS",
            help=f"Poll interval for continuous mode (default: {default_interval}s)",
        )
        parser.add_argument(
            "--dir",
            type=Path,
            default=base_dir,
            metavar="PATH",
            help="Vault root directory (default: directory containing this script)",
        )
        args = parser.parse_args()

        effective_dir = args.dir or base_dir or Path(__file__).resolve().parent
        return cls(
            base_dir=effective_dir,
            poll_interval=args.interval,
            one_shot=args.once,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _backoff_delay(self) -> float:
        """
        Return backoff seconds: doubles each consecutive error, capped at _MAX_BACKOFF.
        First error gets no backoff (return 0.0) — only repeated failures sleep.
        """
        if self._consecutive_errors <= 1:
            return 0.0
        delay = self.poll_interval * (self._BACKOFF_FACTOR ** (self._consecutive_errors - 1))
        return min(delay, self._MAX_BACKOFF)
