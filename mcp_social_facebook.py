"""
MCP Social – Facebook Integration Stub.

Simulates posting to Facebook via the Graph API.
No real token required — all calls are dry-run stubs with full audit logging.

Usage:
    tool = SocialFacebookTool()
    result = tool.post_message("Hello from AI Employee Vault!")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from audit_logger import log_action

SERVER_NAME  = "mcp_social_facebook"
BASE_DIR     = Path(__file__).resolve().parent
LOGS_DIR     = BASE_DIR / "Logs"
SOCIAL_LOG   = LOGS_DIR / "social_facebook.json"

# Stub: replace with a real page token from Graph API Explorer
_FB_PAGE_TOKEN = ""


class SocialFacebookTool:
    """MCP tool for Facebook post operations (stub — no real token required)."""

    def post_message(self, message: str) -> dict:
        """
        Simulate posting a message to a Facebook Page.

        Args:
            message: The text to post.

        Returns:
            dict with platform, status, message, summary, and timestamp.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            if not message or not message.strip():
                raise ValueError("message must be a non-empty string")

            summary = self._generate_summary(message)

            result = {
                "platform":  "facebook",
                "status":    "posted",
                "message":   message.strip(),
                "summary":   summary,
                "timestamp": timestamp,
            }

            self._write_social_log(result)
            log_action(
                SERVER_NAME,
                "post_message",
                {"platform": "facebook", "chars": len(message), "summary": summary},
            )
            return result

        except Exception as exc:
            error_result = {
                "platform":  "facebook",
                "status":    "error",
                "message":   message,
                "summary":   "",
                "timestamp": timestamp,
                "error":     str(exc),
            }
            log_action(
                SERVER_NAME,
                "post_message_error",
                {"platform": "facebook", "error": str(exc)},
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
        """Append entry to /Logs/social_facebook.json (JSON array on disk)."""
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
    tool = SocialFacebookTool()
    out = tool.post_message("Announcing the AI Employee Vault Gold Tier — now live!")
    print(json.dumps(out, indent=2))
