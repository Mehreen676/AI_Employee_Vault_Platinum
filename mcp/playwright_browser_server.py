"""
mcp/playwright_browser_server.py — Playwright Browser MCP Server (Gold Tier).

Exposes four tools registered in the MCP tool registry:

    open_url         Navigate to a URL; return page title + final URL.
    click_selector   Click a CSS selector or XPath on the loaded page.
    type_text        Type text into an element identified by CSS selector.
    screenshot       Capture a full-page PNG and save it to disk.

DRY_RUN mode (MCP_DRY_RUN=true, the default)
---------------------------------------------
No real browser is launched. Full intent is logged via audit_logger.
Returns a clearly-marked simulated result dict.
Safe for CI, staging, and agents without Playwright installed.

Live mode (MCP_DRY_RUN=false)
------------------------------
Real Playwright session — chromium by default, headless by default.
Each tool call is stateless: it opens its own browser, acts, then closes.
Requires:
    pip install playwright
    python -m playwright install chromium

Environment variables
---------------------
    MCP_DRY_RUN              "false" to enable live browsing  (default: "true")
    PLAYWRIGHT_BROWSER       chromium | firefox | webkit       (default: chromium)
    PLAYWRIGHT_HEADLESS      true | false                      (default: true)
    PLAYWRIGHT_TIMEOUT_MS    Navigation + selector timeout ms  (default: 30000)
    PLAYWRIGHT_SCREENSHOT_DIR Directory for saved PNGs         (default: Screenshots/)
    PLAYWRIGHT_SLOW_MO_MS    Slow-motion delay in ms           (default: 0)
    PLAYWRIGHT_USER_AGENT    Custom User-Agent string          (optional)

See docs/BROWSER_SETUP.md for full setup, demo, and troubleshooting guide.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from audit_logger import log_action
from mcp.registry import register

SERVER_NAME     = "playwright_browser_server"
_SCREENSHOT_DIR = Path(os.getenv("PLAYWRIGHT_SCREENSHOT_DIR", "Screenshots"))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _browser_config() -> dict:
    """Read Playwright env vars and return a config dict."""
    return {
        "browser":    os.getenv("PLAYWRIGHT_BROWSER",    "chromium").lower(),
        "headless":   os.getenv("PLAYWRIGHT_HEADLESS",   "true").lower() != "false",
        "timeout_ms": int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000")),
        "slow_mo":    int(os.getenv("PLAYWRIGHT_SLOW_MO_MS",  "0")),
        "user_agent": os.getenv("PLAYWRIGHT_USER_AGENT", ""),
    }


def _launch(cfg: dict):
    """
    Launch a Playwright browser and return (pw, browser, page).

    Caller MUST call  browser.close(); pw.stop()  in a finally block.

    Raises ImportError if playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Playwright not installed.\n"
            "Run:  pip install playwright && python -m playwright install chromium"
        ) from exc

    pw      = sync_playwright().start()
    launcher = getattr(pw, cfg["browser"], pw.chromium)
    browser  = launcher.launch(headless=cfg["headless"], slow_mo=cfg["slow_mo"])

    ctx_opts: dict = {}
    if cfg["user_agent"]:
        ctx_opts["user_agent"] = cfg["user_agent"]

    ctx  = browser.new_context(**ctx_opts)
    ctx.set_default_timeout(cfg["timeout_ms"])
    page = ctx.new_page()
    return pw, browser, page


def _error_result(action_type: str, dry_run: bool, message: str, task_file: str) -> dict:
    log_action(SERVER_NAME, f"{action_type}_error",
               {"task_file": task_file, "error": message}, success=False)
    return {
        "server":      SERVER_NAME,
        "action_type": action_type,
        "dry_run":     dry_run,
        "result":      "error",
        "message":     message,
        "timestamp":   _now(),
    }


# ── Tool: open_url ────────────────────────────────────────────────────────────

def handle_open_url(payload: dict, dry_run: bool = True) -> dict:
    """
    Navigate to a URL and return the page title + final URL after redirects.

    Required payload keys:
        url         Target URL (must be http:// or https://)

    Optional payload keys:
        wait_until  "load" | "domcontentloaded" | "networkidle"  (default: "load")
        task_file   Originating task filename (for audit logging)
    """
    now       = _now()
    task_file = payload.get("task_file", payload.get("task_name", "unknown"))
    url       = payload.get("url", "").strip()
    wait_for  = payload.get("wait_until", "load")

    if not url:
        return _error_result("open_url", dry_run, "open_url requires a 'url' in payload.", task_file)
    if not url.startswith(("http://", "https://")):
        return _error_result("open_url", dry_run,
                             f"open_url: URL must start with http:// or https://, got: {url!r}",
                             task_file)

    # ── DRY RUN ───────────────────────────────────────────────────────────────
    if dry_run:
        result: dict = {
            "server":      SERVER_NAME,
            "action_type": "open_url",
            "dry_run":     True,
            "result":      "dry_run_logged",
            "message":     f"[DRY RUN] Would open URL: {url!r}",
            "timestamp":   now,
            "intent":      {"url": url, "wait_until": wait_for, "task_file": task_file},
        }
        log_action(SERVER_NAME, "open_url_dry_run", {
            "task_file": task_file, "url": url, "wait_until": wait_for,
            "dry_run": True, "note": "Set MCP_DRY_RUN=false to open real URLs.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would open URL")
        print(f"  [{SERVER_NAME}]   URL:        {url}")
        print(f"  [{SERVER_NAME}]   wait_until: {wait_for}")
        print(f"  [{SERVER_NAME}]   Task:       {task_file}")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")
        return result

    # ── LIVE ──────────────────────────────────────────────────────────────────
    cfg = _browser_config()
    pw = browser = None
    try:
        pw, browser, page = _launch(cfg)
        page.goto(url, wait_until=wait_for)
        final_url = page.url
        title     = page.title()

        result = {
            "server":      SERVER_NAME,
            "action_type": "open_url",
            "dry_run":     False,
            "result":      "success",
            "message":     f"Opened {url!r} — title: {title!r}",
            "url":         final_url,
            "title":       title,
            "timestamp":   now,
        }
        log_action(SERVER_NAME, "open_url_success", {
            "task_file": task_file, "url": final_url, "title": title,
        })
        print(f"  [{SERVER_NAME}] Opened: {final_url!r}  title={title!r}")

    except Exception as exc:
        result = _error_result("open_url", False, str(exc), task_file)
        print(f"  [{SERVER_NAME}] ERROR in open_url: {exc}")
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()

    return result


# ── Tool: click_selector ──────────────────────────────────────────────────────

def handle_click_selector(payload: dict, dry_run: bool = True) -> dict:
    """
    Navigate to a URL then click a CSS selector or XPath expression.

    Required payload keys:
        url         Page to navigate to first
        selector    CSS selector  (e.g. "button#submit")  OR
                    XPath string  (e.g. "//button[text()='OK']")

    Optional payload keys:
        wait_until  "load" | "domcontentloaded" | "networkidle"  (default: "load")
        task_file   Originating task filename
    """
    now       = _now()
    task_file = payload.get("task_file", payload.get("task_name", "unknown"))
    url       = payload.get("url", "").strip()
    selector  = payload.get("selector", "").strip()
    wait_for  = payload.get("wait_until", "load")

    if not url:
        return _error_result("click_selector", dry_run,
                             "click_selector requires a 'url'.", task_file)
    if not selector:
        return _error_result("click_selector", dry_run,
                             "click_selector requires a 'selector'.", task_file)

    # ── DRY RUN ───────────────────────────────────────────────────────────────
    if dry_run:
        result: dict = {
            "server":      SERVER_NAME,
            "action_type": "click_selector",
            "dry_run":     True,
            "result":      "dry_run_logged",
            "message":     f"[DRY RUN] Would click {selector!r} on {url!r}",
            "timestamp":   now,
            "intent":      {"url": url, "selector": selector, "task_file": task_file},
        }
        log_action(SERVER_NAME, "click_selector_dry_run", {
            "task_file": task_file, "url": url, "selector": selector,
            "dry_run": True, "note": "Set MCP_DRY_RUN=false to perform real clicks.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would click selector")
        print(f"  [{SERVER_NAME}]   URL:      {url}")
        print(f"  [{SERVER_NAME}]   Selector: {selector}")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")
        return result

    # ── LIVE ──────────────────────────────────────────────────────────────────
    cfg = _browser_config()
    pw = browser = None
    try:
        pw, browser, page = _launch(cfg)
        page.goto(url, wait_until=wait_for)
        page.click(selector)
        final_url = page.url

        result = {
            "server":      SERVER_NAME,
            "action_type": "click_selector",
            "dry_run":     False,
            "result":      "success",
            "message":     f"Clicked {selector!r} on {url!r}; now at {final_url!r}",
            "url":         final_url,
            "selector":    selector,
            "timestamp":   now,
        }
        log_action(SERVER_NAME, "click_selector_success", {
            "task_file": task_file, "url": final_url, "selector": selector,
        })
        print(f"  [{SERVER_NAME}] Clicked {selector!r} — now at {final_url!r}")

    except Exception as exc:
        result = _error_result("click_selector", False, str(exc), task_file)
        print(f"  [{SERVER_NAME}] ERROR in click_selector: {exc}")
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()

    return result


# ── Tool: type_text ───────────────────────────────────────────────────────────

def handle_type_text(payload: dict, dry_run: bool = True) -> dict:
    """
    Navigate to a URL, focus a CSS selector, then type text into it.

    Required payload keys:
        url         Page to navigate to first
        selector    CSS selector of the input element  (e.g. "input[name='q']")
        text        Text string to type

    Optional payload keys:
        delay_ms    Per-keystroke delay in ms (simulates human typing, default: 0)
        clear_first Clear existing content before typing (default: true)
        task_file   Originating task filename
    """
    now        = _now()
    task_file  = payload.get("task_file", payload.get("task_name", "unknown"))
    url        = payload.get("url", "").strip()
    selector   = payload.get("selector", "").strip()
    text       = payload.get("text", "")
    delay_ms   = int(payload.get("delay_ms", 0))
    clear_first = str(payload.get("clear_first", "true")).lower() != "false"

    if not url:
        return _error_result("type_text", dry_run,
                             "type_text requires a 'url'.", task_file)
    if not selector:
        return _error_result("type_text", dry_run,
                             "type_text requires a 'selector'.", task_file)
    if not text:
        return _error_result("type_text", dry_run,
                             "type_text requires a non-empty 'text'.", task_file)

    preview = text[:60] + ("…" if len(text) > 60 else "")

    # ── DRY RUN ───────────────────────────────────────────────────────────────
    if dry_run:
        result: dict = {
            "server":      SERVER_NAME,
            "action_type": "type_text",
            "dry_run":     True,
            "result":      "dry_run_logged",
            "message":     f"[DRY RUN] Would type into {selector!r} on {url!r}",
            "timestamp":   now,
            "intent": {
                "url": url, "selector": selector,
                "text_preview": preview, "task_file": task_file,
            },
        }
        log_action(SERVER_NAME, "type_text_dry_run", {
            "task_file": task_file, "url": url, "selector": selector,
            "text_preview": preview, "dry_run": True,
            "note": "Set MCP_DRY_RUN=false to type into real pages.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would type text")
        print(f"  [{SERVER_NAME}]   URL:      {url}")
        print(f"  [{SERVER_NAME}]   Selector: {selector}")
        print(f"  [{SERVER_NAME}]   Text:     {preview!r}")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")
        return result

    # ── LIVE ──────────────────────────────────────────────────────────────────
    cfg = _browser_config()
    pw = browser = None
    try:
        pw, browser, page = _launch(cfg)
        page.goto(url, wait_until="load")

        if clear_first:
            page.fill(selector, "")

        page.type(selector, text, delay=delay_ms)

        result = {
            "server":      SERVER_NAME,
            "action_type": "type_text",
            "dry_run":     False,
            "result":      "success",
            "message":     f"Typed into {selector!r} on {url!r}",
            "url":         url,
            "selector":    selector,
            "text_preview": preview,
            "timestamp":   now,
        }
        log_action(SERVER_NAME, "type_text_success", {
            "task_file": task_file, "url": url,
            "selector": selector, "text_preview": preview,
        })
        print(f"  [{SERVER_NAME}] Typed into {selector!r}")

    except Exception as exc:
        result = _error_result("type_text", False, str(exc), task_file)
        print(f"  [{SERVER_NAME}] ERROR in type_text: {exc}")
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()

    return result


# ── Tool: screenshot ──────────────────────────────────────────────────────────

def handle_screenshot(payload: dict, dry_run: bool = True) -> dict:
    """
    Navigate to a URL and save a full-page PNG screenshot to disk.

    Required payload keys:
        url         Page to screenshot

    Optional payload keys:
        filename    Output filename (default: screenshot_<timestamp>.png)
        full_page   Capture full scrollable page (default: true)
        wait_until  "load" | "domcontentloaded" | "networkidle"  (default: "networkidle")
        task_file   Originating task filename

    Screenshot is saved to:
        <PLAYWRIGHT_SCREENSHOT_DIR>/<filename>
        Default dir: Screenshots/
    """
    now       = _now()
    task_file = payload.get("task_file", payload.get("task_name", "unknown"))
    url       = payload.get("url", "").strip()
    full_page = str(payload.get("full_page", "true")).lower() != "false"
    wait_for  = payload.get("wait_until", "networkidle")

    if not url:
        return _error_result("screenshot", dry_run,
                             "screenshot requires a 'url'.", task_file)

    # Build output path
    ts_slug   = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_fn = f"screenshot_{ts_slug}.png"
    filename  = payload.get("filename", default_fn)
    if not filename.endswith(".png"):
        filename += ".png"

    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _SCREENSHOT_DIR / filename

    # ── DRY RUN ───────────────────────────────────────────────────────────────
    if dry_run:
        result: dict = {
            "server":          SERVER_NAME,
            "action_type":     "screenshot",
            "dry_run":         True,
            "result":          "dry_run_logged",
            "message":         f"[DRY RUN] Would screenshot {url!r} -> {out_path}",
            "timestamp":       now,
            "intent": {
                "url": url, "output_path": str(out_path),
                "full_page": full_page, "task_file": task_file,
            },
        }
        log_action(SERVER_NAME, "screenshot_dry_run", {
            "task_file": task_file, "url": url,
            "output_path": str(out_path), "full_page": full_page,
            "dry_run": True, "note": "Set MCP_DRY_RUN=false to capture real screenshots.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would take screenshot")
        print(f"  [{SERVER_NAME}]   URL:       {url}")
        print(f"  [{SERVER_NAME}]   Output:    {out_path}")
        print(f"  [{SERVER_NAME}]   full_page: {full_page}")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")
        return result

    # ── LIVE ──────────────────────────────────────────────────────────────────
    cfg = _browser_config()
    pw = browser = None
    try:
        pw, browser, page = _launch(cfg)
        page.goto(url, wait_until=wait_for)
        page.screenshot(path=str(out_path), full_page=full_page)

        file_size = out_path.stat().st_size if out_path.exists() else 0

        result = {
            "server":          SERVER_NAME,
            "action_type":     "screenshot",
            "dry_run":         False,
            "result":          "success",
            "message":         f"Screenshot saved: {out_path} ({file_size} bytes)",
            "screenshot_path": str(out_path),
            "file_size_bytes": file_size,
            "url":             url,
            "timestamp":       now,
        }
        log_action(SERVER_NAME, "screenshot_success", {
            "task_file": task_file, "url": url,
            "screenshot_path": str(out_path), "file_size_bytes": file_size,
        })
        print(f"  [{SERVER_NAME}] Screenshot saved: {out_path} ({file_size:,} bytes)")

    except Exception as exc:
        result = _error_result("screenshot", False, str(exc), task_file)
        print(f"  [{SERVER_NAME}] ERROR in screenshot: {exc}")
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()

    return result


# ── Self-registration (runs at import time) ───────────────────────────────────

register("open_url",        SERVER_NAME, handle_open_url)
register("click_selector",  SERVER_NAME, handle_click_selector)
register("type_text",       SERVER_NAME, handle_type_text)
register("screenshot",      SERVER_NAME, handle_screenshot)
