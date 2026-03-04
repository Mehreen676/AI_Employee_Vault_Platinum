"""
AI Employee Vault – Platinum Tier
Cloud Agent CLI Entry Point

Usage (from backend_api/):
    python run_agent.py
    python run_agent.py --interval 10

Runs the cloud agent queue processor in the foreground.
The same loop also starts automatically as a daemon thread when
the FastAPI server starts (via main.py _startup_init).
"""

import argparse
import logging
import sys
from pathlib import Path

# Allow `python run_agent.py` from backend_api/ without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.cloud_agent import run_cloud_agent_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI Employee Vault – Cloud Agent Queue Processor",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        metavar="SECONDS",
        help="Seconds between processing ticks (default: 5)",
    )
    args = parser.parse_args()

    print(f"[run_agent] Starting cloud agent loop (interval={args.interval}s)")
    print("[run_agent] Press Ctrl-C to stop.\n")

    try:
        run_cloud_agent_loop(interval=args.interval)
    except KeyboardInterrupt:
        print("\n[run_agent] Stopped.")
        sys.exit(0)
