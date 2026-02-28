"""
meta_client.py — Meta Graph API v18 client (Gold Tier).

Thin wrapper around the Meta Graph API v18.0 endpoints used by the
social MCP integration.  No external dependencies — stdlib only
(urllib + json).

Supported operations
--------------------
    MetaClient.from_env()               Build client from env vars.
    client.post_to_facebook_page()      POST to Page feed (text or photo).
    client.post_to_instagram()          Two-step IG media container + publish.
    client.get_page_insights()          GET /{page_id}/insights (best-effort).

Environment variables (set in .env — see .env.example)
-------------------------------------------------------
    META_ACCESS_TOKEN   Page-level access token (used for both FB and IG calls).
    META_PAGE_ID        Numeric Facebook Page ID.
    META_IG_USER_ID     Instagram Business account user ID (for IG posts).
    META_TIMEOUT_S      Network timeout in seconds (default: 30).

Security
--------
Never commit .env.  Page-level tokens expire — refresh via Meta developer
console or a long-lived page token exchange.

See docs/SOCIAL_SETUP.md for the full setup guide.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GRAPH_BASE = "https://graph.facebook.com/v18.0"


# ── Custom exception ──────────────────────────────────────────────────────────

class MetaError(Exception):
    """Raised on HTTP errors, missing credentials, or unexpected API responses."""


# ── Client ────────────────────────────────────────────────────────────────────

class MetaClient:
    """
    Minimal Meta Graph API v18 client.

    Instantiate via MetaClient.from_env() to load credentials from .env.
    All calls use stdlib urllib — no third-party libraries required.
    """

    def __init__(
        self,
        access_token: str,
        page_id:      str,
        ig_user_id:   str = "",
        timeout:      int = 30,
    ) -> None:
        self._token      = access_token
        self._page_id    = page_id
        self._ig_user_id = ig_user_id
        self._timeout    = timeout

    # ── Constructor ───────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "MetaClient":
        """
        Build a MetaClient from environment variables.

        Required: META_ACCESS_TOKEN, META_PAGE_ID
        Optional: META_IG_USER_ID  (needed for Instagram posts)
                  META_TIMEOUT_S   (default: 30)

        Raises MetaError if required vars are missing.
        """
        token      = os.getenv("META_ACCESS_TOKEN", "").strip()
        page_id    = os.getenv("META_PAGE_ID",      "").strip()
        ig_user_id = os.getenv("META_IG_USER_ID",   "").strip()
        timeout    = int(os.getenv("META_TIMEOUT_S", "30"))

        missing = [k for k, v in [("META_ACCESS_TOKEN", token), ("META_PAGE_ID", page_id)] if not v]
        if missing:
            raise MetaError(
                f"Missing required Meta env vars: {', '.join(missing)}.\n"
                "Set them in .env (copy from .env.example).\n"
                "See docs/SOCIAL_SETUP.md for instructions."
            )
        return cls(token, page_id, ig_user_id, timeout)

    # ── Transport helpers ─────────────────────────────────────────────────────

    def _post(self, path: str, params: dict[str, Any]) -> dict:
        """
        HTTP POST to GRAPH_BASE/{path} with form-encoded params + access_token.
        Returns parsed JSON response dict.
        Raises MetaError on HTTP or API errors.
        """
        params["access_token"] = self._token
        body = urllib.parse.urlencode(params).encode("utf-8")
        req  = urllib.request.Request(
            url     = f"{GRAPH_BASE}/{path}",
            data    = body,
            headers = {"Content-Type": "application/x-www-form-urlencoded"},
            method  = "POST",
        )
        return self._execute(req)

    def _get(self, path: str, params: dict[str, Any]) -> dict:
        """
        HTTP GET to GRAPH_BASE/{path}?{params}&access_token=...
        Returns parsed JSON response dict.
        Raises MetaError on HTTP or API errors.
        """
        params["access_token"] = self._token
        qs  = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url    = f"{GRAPH_BASE}/{path}?{qs}",
            method = "GET",
        )
        return self._execute(req)

    def _execute(self, req: urllib.request.Request) -> dict:
        """Shared HTTP execution + error handling."""
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                api_err = json.loads(raw).get("error", {})
                msg = api_err.get("message") or raw
            except Exception:
                msg = raw
            raise MetaError(f"Meta API HTTP {exc.code}: {msg}") from exc
        except urllib.error.URLError as exc:
            raise MetaError(
                f"Cannot reach Meta Graph API: {exc.reason}\n"
                "Check network connectivity and META_ACCESS_TOKEN."
            ) from exc
        except Exception as exc:
            raise MetaError(f"Meta API transport error: {exc}") from exc

    # ── Facebook ──────────────────────────────────────────────────────────────

    def post_to_facebook_page(
        self,
        message:   str,
        link:      str | None = None,
        image_url: str | None = None,
    ) -> str:
        """
        Publish a post to the configured Facebook Page feed.

        If image_url is provided, POSTs to /{page_id}/photos (photo + caption).
        Otherwise POSTs to /{page_id}/feed (text ± link).

        Returns:
            str — the new post ID (e.g. "123456789_987654321")
        """
        if image_url:
            resp = self._post(f"{self._page_id}/photos", {
                "url":     image_url,
                "caption": message,
            })
        else:
            params: dict[str, Any] = {"message": message}
            if link:
                params["link"] = link
            resp = self._post(f"{self._page_id}/feed", params)

        post_id = resp.get("id") or resp.get("post_id") or ""
        if not post_id:
            raise MetaError(f"Facebook post succeeded but returned no ID: {resp}")
        return str(post_id)

    # ── Instagram ─────────────────────────────────────────────────────────────

    def post_to_instagram(self, image_url: str, caption: str = "") -> str:
        """
        Publish a photo post to the configured Instagram Business account.

        Two-step process (Meta Content Publishing API):
            1. POST /{ig_user_id}/media          → creation_id (media container)
            2. POST /{ig_user_id}/media_publish  → post_id

        Args:
            image_url: Public HTTPS URL of the image to post.
            caption:   Post caption text (optional).

        Returns:
            str — the published IG media ID.

        Raises MetaError if META_IG_USER_ID is not configured or any step fails.
        """
        if not self._ig_user_id:
            raise MetaError(
                "META_IG_USER_ID is not configured.\n"
                "Set it in .env — see docs/SOCIAL_SETUP.md."
            )

        # Step 1 — create media container
        container = self._post(f"{self._ig_user_id}/media", {
            "image_url": image_url,
            "caption":   caption,
        })
        creation_id = container.get("id", "")
        if not creation_id:
            raise MetaError(f"IG media container returned no creation_id: {container}")

        # Step 2 — publish
        publish = self._post(f"{self._ig_user_id}/media_publish", {
            "creation_id": creation_id,
        })
        post_id = publish.get("id", "")
        if not post_id:
            raise MetaError(f"IG media_publish returned no post ID: {publish}")
        return str(post_id)

    # ── Analytics ─────────────────────────────────────────────────────────────

    def get_page_insights(
        self,
        metrics: list[str] | None = None,
        period:  str = "day",
    ) -> dict:
        """
        Fetch Page-level insights from the Insights API.

        Args:
            metrics: List of metric names (default: page_fans, page_impressions,
                     page_post_engagements).
            period:  Aggregation window: "day" | "week" | "days_28" | "month".

        Returns:
            Raw API response dict.  Callers should handle gracefully when
            the page has no published posts or insufficient data (HTTP 400).

        Raises MetaError on network failure or unexpected errors.
        """
        m = metrics or ["page_fans", "page_impressions", "page_post_engagements"]
        return self._get(f"{self._page_id}/insights", {
            "metric": ",".join(m),
            "period": period,
        })
