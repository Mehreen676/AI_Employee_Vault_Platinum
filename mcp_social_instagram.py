"""
MCP Social – Instagram Integration Stub.

Simulates posting to Instagram via the Meta Graph API.
No real token required — all calls are dry-run stubs with full audit logging.

Usage:
    tool = SocialInstagramTool()
    result = tool.post_message("Hello from AI Employee Vault!")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from audit_logger import log_action

SERVER_NAME  = "mcp_social_instagram"
BASE_DIR     = Path(__file__).resolve().parent
LOGS_DIR     = BASE_DIR / "Logs"
SOCIAL_LOG   = LOGS_DIR / "social_instagram.json"

# Stub: replace with a real Instagram Business Account token
_IG_ACCESS_TOKEN = ""


class SocialInstagramTool:
    """MCP tool for Instagram post operations (stub — no real token required)."""

    def post_message(self, message: str) -> dict:
        """
        Simulate posting a caption/message to an Instagram Business account.

        Args:
            message: The caption text to post.

        Returns:
            dict with platform, status, message, summary, and timestamp.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            if not message or not message.strip():
                raise ValueError("message must be a non-empty string")

            summary = self._generate_summary(message)

            result = {
                "platform":  "instagram",
                "status":    "posted",
                "message":   message.strip(),
                "summary":   summary,
                "timestamp": timestamp,
            }

            self._write_social_log(result)
            log_action(
                SERVER_NAME,
                "post_message",
                {"platform": "instagram", "chars": len(message), "summary": summary},
            )
            return result

        except Exception as exc:
            error_result = {
                "platform":  "instagram",
                "status":    "error",
                "message":   message,
                "summary":   "",
                "timestamp": timestamp,
                "error":     str(exc),
            }
            log_action(
                SERVER_NAME,
                "post_message_error",
                {"platform": "instagram", "error": str(exc)},
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
        """Append entry to /Logs/social_instagram.json (JSON array on disk)."""
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
    tool = SocialInstagramTool()
    out = tool.post_message("Gold Tier AI Employee Vault is live. Autonomous. Audited. 🚀")
    print(json.dumps(out, indent=2))
