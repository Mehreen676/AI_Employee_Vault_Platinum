"""
mcp/social_mcp_stub.py — Meta Graph API v18 + X API v2 + Social MCP (Gold Tier).

Provides real social media posting when MCP_DRY_RUN=false:
    Facebook Page  — Meta Graph API v18.0
    Instagram      — Meta Content Publishing API v18.0 (two-step)
    Twitter/X      — X API v2  POST /2/tweets

All actions pass through the standard HITL approval flow before
dispatch_action() calls this stub.

DRY_RUN=true  (default, controlled by MCP_DRY_RUN env var)
    Logs intent to audit_logger + Logs/<timestamp>.json.
    No network calls to any platform API.
    Safe for CI, staging, and demo environments.

DRY_RUN=false
    Facebook/Instagram: meta_client.MetaClient.from_env()
        Requires META_ACCESS_TOKEN, META_PAGE_ID (+ META_IG_USER_ID for IG).
    Twitter/X: x_client.XClient.from_env()
        Requires X_BEARER_TOKEN.

Registered action_types
-----------------------
    social_post_facebook    — Post to Facebook Page feed (text or photo).
    social_post_instagram   — Two-step IG media container + publish.
    social_post_twitter     — POST /2/tweets via X API v2.
    social_get_analytics    — Meta Page insights; falls back to "not_available".

Environment variables (required only when MCP_DRY_RUN=false)
------------------------------------------------------------
    META_ACCESS_TOKEN   Page-level access token (Facebook + Instagram).
    META_PAGE_ID        Numeric Facebook Page ID.
    META_IG_USER_ID     Instagram Business account user ID (for IG posts).
    X_BEARER_TOKEN      X API v2 Bearer Token (tweet.write scope required).

See docs/SOCIAL_SETUP.md for credential setup and token generation.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone

from audit_logger import log_action
from mcp.registry import register

SERVER_NAME = "social_mcp_stub"


# ── Simulated analytics (used in dry_run + analytics fallback) ────────────────

_SIMULATED_ANALYTICS: dict[str, dict] = {
    "facebook": {
        "followers":        4_820,
        "reach_30d":       12_400,
        "impressions_30d": 38_900,
        "engagements_30d":  1_230,
        "top_post_reach":   5_600,
    },
    "instagram": {
        "followers":        7_310,
        "reach_30d":       18_750,
        "impressions_30d": 52_100,
        "engagements_30d":  2_890,
        "top_post_reach":   9_200,
    },
    "twitter": {
        "followers":        2_140,
        "reach_30d":        8_300,
        "impressions_30d": 24_600,
        "engagements_30d":    670,
        "top_post_reach":   3_400,
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _simulated_post_id(platform: str) -> str:
    suffix = random.randint(10_000_000_000, 99_999_999_999)
    prefixes = {"facebook": "fb", "instagram": "ig", "twitter": "tw"}
    return f"{prefixes.get(platform, 'sm')}_{suffix}_simulated"


def _get_client():
    """Import and instantiate MetaClient from env. Raises MetaError on failure."""
    from meta_client import MetaClient
    return MetaClient.from_env()


def _error_result(action_type: str, dry_run: bool, message: str, task_file: str) -> dict:
    return {
        "server":      SERVER_NAME,
        "action_type": action_type,
        "dry_run":     dry_run,
        "result":      "error",
        "task_file":   task_file,
        "message":     message,
        "timestamp":   _now(),
    }


# ── Handlers ──────────────────────────────────────────────────────────────────

def handle_social_post_facebook(payload: dict, dry_run: bool = True) -> dict:
    """
    Post to a Facebook Page feed via Meta Graph API v18.

    Expected payload keys:
        content     — post text (required for live mode)
        image_url   — optional public image URL
        link        — optional link to attach
        task_file   — originating task filename (audit)
    """
    task_file = payload.get("task_file", "unknown")
    content   = payload.get("content",   "<no content provided>")
    image_url = payload.get("image_url") or None
    link      = payload.get("link")      or None

    if dry_run:
        sim_id = _simulated_post_id("facebook")
        result: dict = {
            "server":             SERVER_NAME,
            "action_type":        "social_post_facebook",
            "dry_run":            True,
            "result":             "dry_run_logged",
            "simulated_post_id":  sim_id,
            "message":            f"[DRY RUN] Would post to Facebook Page — task: {task_file!r}",
            "timestamp":          _now(),
            "intent": {
                "platform":        "facebook",
                "content_preview": content[:120],
                "image_url":       image_url,
                "task_file":       task_file,
            },
        }
        log_action(SERVER_NAME, "social_post_facebook_dry_run", {
            "request":  {"message": content[:120], "image_url": image_url, "link": link},
            "response": "dry_run — no network call",
            "task_file": task_file,
            "dry_run":  True,
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would post to Facebook Page")
        print(f"  [{SERVER_NAME}]   Content: {content[:80]}...")
        return result

    # ── Real Meta Graph API call ──
    request_details = {
        "action_type": "social_post_facebook",
        "api":         "Meta Graph API v18.0",
        "endpoint":    f"/{os.getenv('META_PAGE_ID', '?')}/feed",
        "request":     {"message": content[:240], "image_url": image_url, "link": link},
        "task_file":   task_file,
        "dry_run":     False,
    }
    try:
        client  = _get_client()
        post_id = client.post_to_facebook_page(
            message=content, link=link, image_url=image_url
        )
        result = {
            "server":      SERVER_NAME,
            "action_type": "social_post_facebook",
            "dry_run":     False,
            "result":      "posted",
            "post_id":     post_id,
            "message":     f"Posted to Facebook Page: post_id={post_id}",
            "timestamp":   _now(),
        }
        log_action(SERVER_NAME, "social_post_facebook_ok", {
            **request_details,
            "response": {"post_id": post_id, "status": "posted"},
        })
        print(f"  [{SERVER_NAME}] Posted to Facebook Page: post_id={post_id}")
        return result
    except Exception as exc:
        log_action(SERVER_NAME, "social_post_facebook_error", {
            **request_details,
            "response": {"error": str(exc)},
        }, success=False)
        print(f"  [{SERVER_NAME}] ERROR posting to Facebook: {exc}")
        return _error_result("social_post_facebook", False, str(exc), task_file)


def handle_social_post_instagram(payload: dict, dry_run: bool = True) -> dict:
    """
    Post a photo to Instagram Business via Meta Graph API v18 (two-step).

    Step 1: POST /{ig_user_id}/media           → creation_id
    Step 2: POST /{ig_user_id}/media_publish   → post_id

    Expected payload keys:
        image_url   — public HTTPS image URL (required for live mode)
        caption     — post caption text
        task_file   — originating task filename (audit)
    """
    task_file = payload.get("task_file", "unknown")
    caption   = payload.get("caption",   payload.get("content", "<no caption provided>"))
    image_url = payload.get("image_url") or ""

    if dry_run:
        sim_id = _simulated_post_id("instagram")
        result: dict = {
            "server":             SERVER_NAME,
            "action_type":        "social_post_instagram",
            "dry_run":            True,
            "result":             "dry_run_logged",
            "simulated_post_id":  sim_id,
            "message":            f"[DRY RUN] Would post to Instagram — task: {task_file!r}",
            "timestamp":          _now(),
            "intent": {
                "platform":       "instagram",
                "caption_preview": caption[:120],
                "image_url":      image_url,
                "task_file":      task_file,
            },
        }
        log_action(SERVER_NAME, "social_post_instagram_dry_run", {
            "request":  {"image_url": image_url, "caption": caption[:120]},
            "response": "dry_run — no network call",
            "task_file": task_file,
            "dry_run":  True,
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would post to Instagram")
        print(f"  [{SERVER_NAME}]   Caption: {caption[:80]}...")
        return result

    # ── Real two-step Meta Graph API call ──
    if not image_url:
        msg = "social_post_instagram requires 'image_url' in payload for live mode."
        log_action(SERVER_NAME, "social_post_instagram_error", {
            "request":  {"caption": caption[:120]},
            "response": {"error": msg},
            "task_file": task_file,
            "dry_run":   False,
        }, success=False)
        return _error_result("social_post_instagram", False, msg, task_file)

    request_details = {
        "action_type": "social_post_instagram",
        "api":         "Meta Graph API v18.0 (Content Publishing)",
        "endpoint":    f"/{os.getenv('META_IG_USER_ID', '?')}/media + /media_publish",
        "request":     {"image_url": image_url, "caption": caption[:240]},
        "task_file":   task_file,
        "dry_run":     False,
    }
    try:
        client  = _get_client()
        post_id = client.post_to_instagram(image_url=image_url, caption=caption)
        result = {
            "server":      SERVER_NAME,
            "action_type": "social_post_instagram",
            "dry_run":     False,
            "result":      "posted",
            "post_id":     post_id,
            "message":     f"Posted to Instagram: post_id={post_id}",
            "timestamp":   _now(),
        }
        log_action(SERVER_NAME, "social_post_instagram_ok", {
            **request_details,
            "response": {"post_id": post_id, "status": "posted"},
        })
        print(f"  [{SERVER_NAME}] Posted to Instagram: post_id={post_id}")
        return result
    except Exception as exc:
        log_action(SERVER_NAME, "social_post_instagram_error", {
            **request_details,
            "response": {"error": str(exc)},
        }, success=False)
        print(f"  [{SERVER_NAME}] ERROR posting to Instagram: {exc}")
        return _error_result("social_post_instagram", False, str(exc), task_file)


def handle_social_post_twitter(payload: dict, dry_run: bool = True) -> dict:
    """
    Post a tweet via X API v2  POST /2/tweets.

    DRY_RUN=true  → logs intent, no network call.
    DRY_RUN=false → real POST /2/tweets with Bearer Token auth.
                    Requires X_BEARER_TOKEN in .env.

    Expected payload keys:
        text        — tweet text (max 280 chars; auto-truncated)
        content     — alias for text
        task_file   — originating task filename (audit)
    """
    task_file = payload.get("task_file", "unknown")
    text      = payload.get("text", payload.get("content", "<no text provided>"))
    account   = payload.get("account", "@AIEmployeeVault")

    if dry_run:
        sim_id = _simulated_post_id("twitter")
        result: dict = {
            "server":             SERVER_NAME,
            "action_type":        "social_post_twitter",
            "dry_run":            True,
            "result":             "dry_run_logged",
            "simulated_tweet_id": sim_id,
            "message":            f"[DRY RUN] Would tweet from {account!r} — task: {task_file!r}",
            "timestamp":          _now(),
            "intent": {
                "platform":     "twitter",
                "text_preview": text[:120],
                "char_count":   len(text),
                "task_file":    task_file,
            },
        }
        log_action(SERVER_NAME, "social_post_twitter_dry_run", {
            "request":  {"text": text[:120]},
            "response": "dry_run — no network call",
            "task_file": task_file,
            "dry_run":   True,
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would tweet via X API v2")
        print(f"  [{SERVER_NAME}]   Text: {text[:80]}...")
        return result

    # ── Real X API v2 call ──
    request_details = {
        "action_type": "social_post_twitter",
        "api":         "X API v2",
        "endpoint":    "POST /2/tweets",
        "request":     {"text": text[:120]},
        "task_file":   task_file,
        "dry_run":     False,
    }
    try:
        from x_client import XClient
        client = XClient.from_env()
        resp   = client.post_tweet(text)
        result = {
            "server":      SERVER_NAME,
            "action_type": "social_post_twitter",
            "dry_run":     False,
            "result":      "posted",
            "tweet_id":    resp["tweet_id"],
            "text":        resp["text"],
            "message":     f"Tweeted via X API v2: tweet_id={resp['tweet_id']}",
            "timestamp":   _now(),
        }
        log_action(SERVER_NAME, "social_post_twitter_ok", {
            **request_details,
            "response": resp["raw"],
        })
        print(f"  [{SERVER_NAME}] Tweeted via X API v2: tweet_id={resp['tweet_id']}")
        return result
    except Exception as exc:
        log_action(SERVER_NAME, "social_post_twitter_error", {
            **request_details,
            "response": {"error": str(exc)},
        }, success=False)
        print(f"  [{SERVER_NAME}] ERROR posting tweet: {exc}")
        return _error_result("social_post_twitter", False, str(exc), task_file)


def handle_social_get_analytics(payload: dict, dry_run: bool = True) -> dict:
    """
    Retrieve Facebook Page insights via Meta Graph API v18.

    DRY_RUN=true  → returns simulated analytics data (no API call).
    DRY_RUN=false → calls /{page_id}/insights; falls back to "not_available"
                    with a log entry if the API returns an error.

    Expected payload keys:
        platform    — "facebook" | "instagram" | "twitter" | "all"
        period      — "day" | "week" | "days_28" | "month" (default: "day")
        task_file   — originating task filename (audit)
    """
    task_file = payload.get("task_file", "unknown")
    platform  = payload.get("platform", "all").lower()
    period    = payload.get("period",   "day")

    if dry_run:
        analytics = (
            _SIMULATED_ANALYTICS.copy()
            if platform == "all"
            else {platform: _SIMULATED_ANALYTICS.get(platform, {})}
        )
        result: dict = {
            "server":      SERVER_NAME,
            "action_type": "social_get_analytics",
            "dry_run":     True,
            "result":      "simulated_analytics",
            "analytics":   analytics,
            "period":      period,
            "message":     f"[SIMULATED] Analytics for platform={platform!r}, period={period!r}",
            "timestamp":   _now(),
            "note":        "Simulated data. Set MCP_DRY_RUN=false for real Meta insights.",
        }
        log_action(SERVER_NAME, "social_get_analytics_dry_run", {
            "request":  {"platform": platform, "period": period},
            "response": "dry_run — simulated analytics returned",
            "task_file": task_file,
            "dry_run":   True,
        })
        print(f"  [{SERVER_NAME}] SIMULATED analytics: platform={platform!r}")
        for p, data in analytics.items():
            print(f"  [{SERVER_NAME}]   {p}: followers={data.get('followers', 'n/a')}")
        return result

    # ── Real Meta Insights API call ──
    request_details = {
        "action_type": "social_get_analytics",
        "api":         "Meta Graph API v18.0 Insights",
        "endpoint":    f"/{os.getenv('META_PAGE_ID', '?')}/insights",
        "request":     {"platform": platform, "period": period},
        "task_file":   task_file,
        "dry_run":     False,
    }
    try:
        client   = _get_client()
        raw      = client.get_page_insights(period=period)
        # Normalise the API response into a flat dict
        insights: dict = {}
        for item in raw.get("data", []):
            name   = item.get("name", "unknown")
            values = item.get("values", [])
            latest = values[-1].get("value", 0) if values else 0
            insights[name] = latest

        result = {
            "server":      SERVER_NAME,
            "action_type": "social_get_analytics",
            "dry_run":     False,
            "result":      "ok",
            "analytics":   {"facebook": insights},
            "period":      period,
            "message":     f"Fetched Meta Page insights for period={period!r}",
            "timestamp":   _now(),
        }
        log_action(SERVER_NAME, "social_get_analytics_ok", {
            **request_details,
            "response": {"insights_keys": list(insights.keys())},
        })
        print(f"  [{SERVER_NAME}] Meta insights fetched: {list(insights.keys())}")
        return result

    except Exception as exc:
        # Graceful fallback — insights may not be available for all pages/tokens
        not_avail_msg = (
            f"Meta insights not available (period={period!r}): {exc}. "
            "Returning not_available."
        )
        log_action(SERVER_NAME, "social_get_analytics_not_available", {
            **request_details,
            "response": {"error": str(exc), "fallback": "not_available"},
        }, success=False)
        print(f"  [{SERVER_NAME}] Analytics not available: {exc}")
        return {
            "server":      SERVER_NAME,
            "action_type": "social_get_analytics",
            "dry_run":     False,
            "result":      "not_available",
            "message":     not_avail_msg,
            "timestamp":   _now(),
        }


# ── Self-registration (runs at import time) ───────────────────────────────────

register("social_post_facebook",  SERVER_NAME, handle_social_post_facebook)
register("social_post_instagram", SERVER_NAME, handle_social_post_instagram)
register("social_post_twitter",   SERVER_NAME, handle_social_post_twitter)
register("social_get_analytics",  SERVER_NAME, handle_social_get_analytics)
