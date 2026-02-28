"""
MCP Social – Twitter / X Integration Stub.

Simulates posting a tweet via the Twitter API v2.
No real token required — all calls are dry-run stubs with full audit logging.

Usage:
    tool = SocialTwitterTool()
    result = tool.post_message("Hello from AI Employee Vault!")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from audit_logger import log_action

SERVER_NAME  = "mcp_social_twitter"
BASE_DIR     = Path(__file__).resolve().parent
LOGS_DIR     = BASE_DIR / "Logs"
SOCIAL_LOG   = LOGS_DIR / "social_twitter.json"

# Twitter API v2 limits: 280 chars per tweet
_TWEET_MAX_CHARS = 280

# Stub: replace with real Bearer Token from developer.twitter.com
_TWITTER_BEARER_TOKEN = ""


class SocialTwitterTool:
    """MCP tool for Twitter / X post operations (stub — no real token required)."""

    def post_message(self, message: str) -> dict:
        """
        Simulate posting a tweet to Twitter / X.

        Args:
            message: The tweet text (max 280 characters).

        Returns:
            dict with platform, status, message, summary, and timestamp.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            if not message or not message.strip():
                raise ValueError("message must be a non-empty string")

            cleaned = message.strip()

            if len(cleaned) > _TWEET_MAX_CHARS:
                raise ValueError(
                    f"Tweet exceeds {_TWEET_MAX_CHARS} characters "
                    f"({len(cleaned)} given)"
                )

            summary = self._generate_summary(cleaned)

            result = {
                "platform":  "twitter",
                "status":    "posted",
                "message":   cleaned,
                "summary":   summary,
                "timestamp": timestamp,
            }

            self._write_social_log(result)
            log_action(
                SERVER_NAME,
                "post_message",
                {"platform": "twitter", "chars": len(cleaned), "summary": summary},
            )
            return result

        except Exception as exc:
            error_result = {
                "platform":  "twitter",
                "status":    "error",
                "message":   message,
                "summary":   "",
                "timestamp": timestamp,
                "error":     str(exc),
            }
            log_action(
                SERVER_NAME,
                "post_message_error",
                {"platform": "twitter", "error": str(exc)},
                success=False,
            )
            return error_result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_summary(self, message: str) -> str:
        """Return a short AI-style summary (stub — no real API call)."""
        words = message.strip().split()
        short = " ".join(words[:10])
        suffix = "…" if len(words) > 10 else ""
        return f"[AI Summary] {short}{suffix}"

    def _write_social_log(self, entry: dict) -> None:
        """Append entry to /Logs/social_twitter.json (JSON array on disk)."""
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            existing: list = []
            if SOCIAL_LOG.exists():
                try:
                    existing = json.loads(SOCIAL_LOG.read_text(encoding="utf-8"))
                    if not isinstance(existing, list):
                        existing = []
                except Exception:
                    existing = []
            existing.append(entry)
            SOCIAL_LOG.write_text(
                json.dumps(existing, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass  # never crash on log write failure


if __name__ == "__main__":
    tool = SocialTwitterTool()
    out = tool.post_message("AI Employee Vault Gold Tier — autonomous agent, HITL, MCP, audit logs.")
    print(json.dumps(out, indent=2))
