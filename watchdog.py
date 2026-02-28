"""
AI Employee Vault – Platinum Tier
Health Watchdog — Process Monitor

Module:   watchdog.py
Version:  1.0.0

Responsibility:
    Monitors the three core Platinum Tier processes:
        1. cloud_agent.py        — Cloud Agent (daemon + auto task generation)
        2. watchers/gmail_watcher.py — Gmail inbox feed (Needs_Action/email/)
        3. local_executor.py     — Local task executor (Pending_Approval -> Done)

    For each managed process the watchdog:
        - Tracks liveness via subprocess.Popen.poll().
        - Automatically restarts any process that exits unexpectedly.
        - Writes one structured JSON record to vault/Logs/health_log.json
          per monitoring cycle (JSONL — append-only).
        - Prints a compact health summary to stdout every cycle.

    This is the single entry point for production deployment. Starting the
    watchdog is equivalent to starting the entire Platinum Tier stack.

health_log.json record format (JSONL — one object per line):
    {
        "timestamp":     "<ISO-8601 UTC>",
        "cycle":         <int>,
        "cloud_agent":   {"alive": <bool>, "pid": <int|null>, "restarts": <int>},
        "gmail_watcher": {"alive": <bool>, "pid": <int|null>, "restarts": <int>},
        "local_executor":{"alive": <bool>, "pid": <int|null>, "restarts": <int>}
    }

CLI Usage (from project root):
    python watchdog.py --start-all
    python watchdog.py --start-all --interval 10
    python watchdog.py --start-all --no-gmail
    python watchdog.py --help
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Project root and vault paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent
_VAULT_LOGS   = _PROJECT_ROOT / "vault" / "Logs"
_HEALTH_LOG   = _VAULT_LOGS / "health_log.json"

# Ensure log directory exists before anything else writes to it.
_VAULT_LOGS.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Process command specifications
# ---------------------------------------------------------------------------

_PROCESS_SPECS: dict[str, list[str]] = {
    "cloud_agent": [
        sys.executable,
        str(_PROJECT_ROOT / "cloud_agent.py"),
        "--daemon",
        "--auto",
        "--interval",
        "5",
    ],
    "gmail_watcher": [
        sys.executable,
        "-m",
        "watchers.gmail_watcher",
        "--daemon",
        "--interval",
        "30",
    ],
    "local_executor": [
        sys.executable,
        str(_PROJECT_ROOT / "local_executor.py"),
        "--poll",
        "2",
    ],
}

_PROCESS_LABELS: dict[str, str] = {
    "cloud_agent":    "Cloud Agent    ",
    "gmail_watcher":  "Gmail Watcher  ",
    "local_executor": "Local Executor ",
}

# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------


class Watchdog:
    """
    Starts, monitors, and auto-restarts the Platinum Tier process trio.

    Args:
        interval:     Seconds between health checks. Default: 15.
        enable_gmail: Whether to manage the Gmail watcher. Default: True.
    """

    def __init__(
        self,
        interval: float = 15.0,
        enable_gmail: bool = True,
    ) -> None:
        self._interval     = interval
        self._enable_gmail = enable_gmail

        # Popen handles for each managed process (None = not yet started).
        self._procs: dict[str, Optional[subprocess.Popen]] = {
            "cloud_agent":    None,
            "gmail_watcher":  None,
            "local_executor": None,
        }
        # Cumulative restart counts per process.
        self._restarts: dict[str, int] = {k: 0 for k in self._procs}
        self._cycle = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Start all managed processes and enter the monitoring loop.

        Blocks until CTRL+C, at which point all managed processes are
        terminated gracefully before returning.
        """
        _print_banner(self._interval, self._enable_gmail)
        self._start_all()

        try:
            while True:
                time.sleep(self._interval)
                self._cycle += 1
                self._check_and_restart()
                self._write_health_log()
                self._print_health_summary()

        except KeyboardInterrupt:
            print()
            print("[Watchdog] CTRL+C received. Terminating managed processes...")
            self._terminate_all()
            print("[Watchdog] All processes terminated. Exiting.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _active_names(self) -> list[str]:
        """Return names of the processes this watchdog manages."""
        names = ["cloud_agent", "local_executor"]
        if self._enable_gmail:
            names.append("gmail_watcher")
        return names

    def _start_process(self, name: str) -> None:
        """
        Launch a named process via subprocess.Popen.

        stdout and stderr are redirected to DEVNULL — each process manages
        its own logging to history/prompt_log.json and vault/Logs/.
        """
        cmd = _PROCESS_SPECS[name]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(_PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._procs[name] = proc
            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(
                f"  [{now}] STARTED  {_PROCESS_LABELS[name]}  "
                f"PID={proc.pid}"
            )
        except OSError as exc:
            print(f"  [Watchdog] ERROR starting {name}: {exc}")
            self._procs[name] = None

    def _start_all(self) -> None:
        """Start all managed processes."""
        for name in self._active_names():
            self._start_process(name)

    def _terminate_all(self) -> None:
        """Terminate all managed processes gracefully."""
        for name, proc in self._procs.items():
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
                    print(
                        f"  [{now}] STOPPED  {_PROCESS_LABELS[name]}  "
                        f"PID={proc.pid}"
                    )
                except Exception:
                    pass

    def _check_and_restart(self) -> None:
        """
        Check liveness of all managed processes.

        Any process that has exited (poll() is not None) is immediately
        restarted and its restart counter incremented.
        """
        for name in self._active_names():
            proc = self._procs.get(name)
            if proc is None:
                # Never started — attempt now.
                self._restarts[name] += 1
                self._start_process(name)
            elif proc.poll() is not None:
                # Process has exited unexpectedly.
                now = datetime.now(timezone.utc).strftime("%H:%M:%S")
                rc  = proc.returncode
                print(
                    f"  [{now}] DEAD     {_PROCESS_LABELS[name]}  "
                    f"rc={rc}  -> restarting (restart #{self._restarts[name] + 1})"
                )
                self._restarts[name] += 1
                self._start_process(name)

    def _write_health_log(self) -> None:
        """
        Append one JSONL record to vault/Logs/health_log.json.

        fsync guarantees the write survives a process crash between cycles.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        def _state(name: str) -> dict:
            proc  = self._procs.get(name)
            alive = proc is not None and proc.poll() is None
            pid   = proc.pid if (proc and alive) else None
            return {
                "alive":    alive,
                "pid":      pid,
                "restarts": self._restarts[name],
            }

        record = {
            "timestamp":      now,
            "cycle":          self._cycle,
            "cloud_agent":    _state("cloud_agent"),
            "gmail_watcher":  _state("gmail_watcher"),
            "local_executor": _state("local_executor"),
        }
        with _HEALTH_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _print_health_summary(self) -> None:
        """Print a compact one-line health summary to stdout."""
        now   = datetime.now(timezone.utc).strftime("%H:%M:%S")
        parts = []
        for name in ["cloud_agent", "gmail_watcher", "local_executor"]:
            proc  = self._procs.get(name)
            alive = proc is not None and proc.poll() is None
            label = _PROCESS_LABELS[name].strip()
            parts.append(f"{label}={'UP  ' if alive else 'DOWN'}")
        print(f"  [HB #{self._cycle:04d}] {now}  " + "  |  ".join(parts))


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------


def _print_banner(interval: float, enable_gmail: bool) -> None:
    gmail_label = ", gmail_watcher" if enable_gmail else " (gmail excluded)"
    print()
    print("=" * 64)
    print("  AI Employee Vault - Platinum Tier")
    print("  Health Watchdog v1.0.0 — Process Monitor")
    print("=" * 64)
    print(f"  Monitoring   : cloud_agent, local_executor{gmail_label}")
    print(f"  Check every  : {interval}s")
    print(f"  Health log   : vault/Logs/health_log.json")
    print(f"  Auto-restart : enabled")
    print("=" * 64)
    print("  Press CTRL+C to terminate all managed processes.")
    print()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="watchdog",
        description=(
            "AI Employee Vault - Platinum Tier: Health Watchdog.\n"
            "Starts, monitors, and auto-restarts all three core processes:\n"
            "  cloud_agent.py  |  watchers/gmail_watcher.py  |  local_executor.py\n\n"
            "This is the recommended single entry point for production runs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--start-all",
        action="store_true",
        help=(
            "Start and monitor all processes. "
            "Required — watchdog does nothing without this flag."
        ),
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
        metavar="SECONDS",
        help="Seconds between health checks (default: 15).",
    )
    parser.add_argument(
        "--no-gmail",
        action="store_true",
        help="Exclude the Gmail watcher from monitoring.",
    )

    args = parser.parse_args()

    if not args.start_all:
        parser.print_help()
        print()
        print("Hint: use --start-all to begin monitoring.")
        sys.exit(0)

    dog = Watchdog(
        interval=args.interval,
        enable_gmail=not args.no_gmail,
    )
    dog.run()
