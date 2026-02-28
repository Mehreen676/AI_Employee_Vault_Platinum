@echo off
:: ============================================================
::  run_gmail_watcher.bat — Gmail Inbox Watcher launcher
::  AI Employee Vault Gold Tier
::
::  Usage:
::    scripts\run_gmail_watcher.bat              (infinite loop)
::    scripts\run_gmail_watcher.bat --once       (one-shot / cron)
::    scripts\run_gmail_watcher.bat --interval 30
::
::  Prerequisites:
::    1. py generate_gmail_token.py          (first-time OAuth2 setup)
::    2. .env configured (copy from .env.example)
::    3. pip install -r requirements.txt
::
::  See docs\GMAIL_WATCHER_SETUP.md for full setup instructions.
:: ============================================================

:: Change to repo root (one level up from scripts\)
cd /d "%~dp0.."

echo.
echo ============================================================
echo   Gmail Inbox Watcher -- AI Employee Vault Gold Tier
echo ============================================================
echo.
echo   Repo root : %CD%
echo   Watcher   : watchers\gmail_inbox_watcher.py
echo   Press Ctrl+C to stop.
echo.

:: Pass through any extra arguments (e.g. --once, --interval N)
py watchers\gmail_inbox_watcher.py %*

echo.
echo   Watcher stopped.
pause
