"""
x_client.py — X (Twitter) API v2 client (Gold Tier).

Thin wrapper around the X API v2 tweets endpoint.
No external dependencies — stdlib only (urllib + json).

Supported operations
--------------------
    XClient.from_env()      Build client from env vars.
    client.post_tweet()     POST /2/tweets → returns tweet id + text.

Environment variables (set in .env — see .env.example)
-------------------------------------------------------
    X_BEARER_TOKEN   App Bearer Token from the X Developer Portal.
                     Required for authentication.
    X_TIMEOUT_S      Network timeout in seconds (default: 30).

Authentication note
-------------------
    POST /2/tweets (tweet creation) requires user-context OAuth 2.0
    with the "tweet.write" scope, NOT app-only Bearer Token.

    If your Bearer Token is attached to a user-context OAuth 2.0 app
    and you have exchanged it for a user access token with tweet.write,
    pass that access token as X_BEARER_TOKEN.

    For app-only (read-only) Bearer Tokens, the API will return HTTP 403.
    The client logs the full response body so you can diagnose the error.

    See docs/X_SETUP.md for the full OAuth 2.0 PKCE setup guide.

See also: https://developer.x.com/en/docs/x-api/tweets/manage-tweets/api-reference/post-tweets
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

X_API_BASE = "https://api.twitter.com"


# ── Custom exception ──────────────────────────────────────────────────────────

class XError(Exception):
    """Raised on HTTP errors, missing credentials, or unexpected API responses."""


# ── Client ────────────────────────────────────────────────────────────────────

class XClient:
    """
    Minimal X API v2 client.

    Instantiate via XClient.from_env() to load credentials from .env.
    All calls use stdlib urllib — no third-party libraries required.
    """

    def __init__(self, bearer_token: str, timeout: int = 30) -> None:
        self._token   = bearer_token
        self._timeout = timeout

    # ── Constructor ───────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "XClient":
        """
        Build an XClient from environment variables.

        Required: X_BEARER_TOKEN
        Optional: X_TIMEOUT_S (default: 30)

        Raises XError if X_BEARER_TOKEN is missing.
        """
        token   = os.getenv("X_BEARER_TOKEN", "").strip()
        timeout = int(os.getenv("X_TIMEOUT_S", "30"))

        if not token:
            raise XError(
                "Missing required env var: X_BEARER_TOKEN.\n"
                "Set it in .env (copy from .env.example).\n"
                "See docs/X_SETUP.md for instructions."
            )
        return cls(token, timeout)

    # ── Transport helper ──────────────────────────────────────────────────────

    def _post_json(self, path: str, body: dict[str, Any]) -> dict:
        """
        HTTP POST to X_API_BASE/{path} with JSON body and Bearer Token auth.
        Returns parsed JSON response dict.
        Raises XError on HTTP or API errors.
        """
        data = json.dumps(body).encode("utf-8")
        req  = urllib.request.Request(
            url     = f"{X_API_BASE}{path}",
            data    = data,
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Content-Type":  "application/json",
            },
            method  = "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                api_err = json.loads(raw)
                detail  = (
                    api_err.get("detail")
                    or api_err.get("title")
                    or api_err.get("errors", [{}])[0].get("message", "")
                    or raw
                )
            except Exception:
                detail = raw
            raise XError(f"X API HTTP {exc.code}: {detail}  (raw={raw[:300]})") from exc
        except urllib.error.URLError as exc:
            raise XError(
                f"Cannot reach X API: {exc.reason}\n"
                "Check network connectivity and X_BEARER_TOKEN."
            ) from exc
        except Exception as exc:
            raise XError(f"X API transport error: {exc}") from exc

    # ── Tweets ────────────────────────────────────────────────────────────────

    def post_tweet(self, text: str) -> dict:
        """
        Create a tweet via POST /2/tweets.

        Args:
            text: Tweet text (max 280 characters for standard tweets).

        Returns:
            dict with keys:
                tweet_id  (str)   — the new tweet's ID
                text      (str)   — the posted text (as confirmed by the API)
                raw       (dict)  — full API response for audit logging

        Raises XError on failure.
        """
        if len(text) > 280:
            text = text[:277] + "..."

        resp = self._post_json("/2/tweets", {"text": text})

        data     = resp.get("data", {})
        tweet_id = data.get("id", "")
        if not tweet_id:
            raise XError(f"X API returned no tweet id: {resp}")

        return {
            "tweet_id": tweet_id,
            "text":     data.get("text", text),
            "raw":      resp,
        }
