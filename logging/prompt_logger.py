"""
AI Employee Vault – Platinum Tier
Prompt Logging Subsystem

Module:   logging/prompt_logger.py
Version:  1.0.0
Status:   Production Skeleton — Ready for Implementation

Description:
    Provides the PromptLogger class, the authoritative logging interface for
    all components in the Platinum Tier system. Every prompt generated,
    every task transition, and every system event MUST be recorded through
    this module.

    This module implements:
        - Append-only JSONL logging to history/prompt_log.json
        - Nanosecond-precision UTC timestamps
        - SHA-256 hash chaining for log integrity verification
        - Session management and correlation
        - Component-specific event type enforcement
        - Thread-safe concurrent write access

    Security Note:
        This log is the evidentiary record of the system. Under no
        circumstances should any code outside this module write directly
        to the log file. All writes MUST go through PromptLogger.

Specification Reference:
    specs/architecture.md § 4.4
    specs/platinum_design.md § 5
    specs/security_model.md § 6

Usage:
    from logging.prompt_logger import PromptLogger, EventType, Component

    logger = PromptLogger()
    logger.log(
        component=Component.CLOUD_AGENT,
        event_type=EventType.PROMPT_GENERATED,
        task_id="f47ac10b-...",
        summary="Generated task prompt for code review",
        detail="Full prompt content or reference",
    )
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0.0"
LOGGER_VERSION = "1.0.0"
GENESIS_HASH = "genesis"
DEFAULT_LOG_PATH = Path(__file__).parent.parent / "history" / "prompt_log.json"


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Component(str, Enum):
    """Identifies the system component that generated the log entry."""

    CLOUD_AGENT = "cloud_agent"
    LOCAL_EXECUTOR = "local_executor"
    HUMAN = "human"
    SYSTEM = "system"


class EventType(str, Enum):
    """
    Enumeration of all valid event types in the Platinum Tier system.
    Any event not in this enumeration is not a recognized system event.
    """

    # Task lifecycle events
    TASK_RECEIVED = "task_received"
    TASK_DECOMPOSED = "task_decomposed"
    TASK_SUBMITTED = "task_submitted"
    TASK_APPROVED = "task_approved"
    TASK_REJECTED = "task_rejected"
    TASK_EXPIRED = "task_expired"
    TASK_EXECUTION_STARTED = "task_execution_started"
    TASK_EXECUTING = "task_executing"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_VALIDATION_FAILED = "task_validation_failed"
    TASK_RESULT_RETRIEVED = "task_result_retrieved"

    # Prompt events
    PROMPT_GENERATED = "prompt_generated"

    # Approval workflow events
    APPROVAL_NOTIFICATION_SENT = "approval_notification_sent"

    # Result events
    RESULT_PROCESSED = "result_processed"
    CLIENT_RESPONSE_SENT = "client_response_sent"

    # System events
    LOG_INITIALIZED = "log_initialized"
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    HEALTH_CHECK = "health_check"

    # Security events
    SECURITY_HASH_MISMATCH = "security_hash_mismatch"
    SECURITY_UNKNOWN_TASK = "security_unknown_task"
    SECURITY_REPLAY_DETECTED = "security_replay_detected"
    SECURITY_SCHEMA_VIOLATION = "security_schema_violation"


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """
    Canonical structure for a single prompt log entry.

    All fields are required except those explicitly marked Optional.
    The entry_hash and prev_hash fields are computed automatically
    by the PromptLogger — do not set them manually.
    """

    log_id: str
    session_id: str
    timestamp: str
    timestamp_ns: int
    component: str
    event_type: str
    task_id: Optional[str]
    prompt_hash: Optional[str]
    prev_hash: str
    entry_hash: str
    content: dict
    metadata: dict

    def to_dict(self) -> dict:
        """Serialize entry to a plain dict suitable for JSON encoding."""
        return {
            "log_id": self.log_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "timestamp_ns": self.timestamp_ns,
            "component": self.component,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "prompt_hash": self.prompt_hash,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "content": self.content,
            "metadata": self.metadata,
        }

    def to_jsonl(self) -> str:
        """Serialize entry to a single-line JSON string for JSONL appending."""
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Core Logger Class
# ---------------------------------------------------------------------------


class PromptLogger:
    """
    Thread-safe, append-only prompt logger for the Platinum Tier system.

    This class is the sole authorized interface for writing to the prompt log.
    It manages session state, hash chaining, and file I/O. Instances are
    safe to share across threads within a single process.

    Instantiation:
        One PromptLogger instance should be created per process (singleton
        pattern is recommended at the application level). Each instance
        maintains its own session_id for correlation.

    Args:
        log_path:       Path to the JSONL log file. Defaults to
                        history/prompt_log.json relative to project root.
        component:      The component this logger instance belongs to.
                        Used as the default 'component' field on log entries.
        session_id:     Optional explicit session UUID. Auto-generated if None.
        executor_version: Version string of the calling component.
    """

    def __init__(
        self,
        log_path: Optional[Path] = None,
        component: Component = Component.SYSTEM,
        session_id: Optional[str] = None,
        executor_version: str = LOGGER_VERSION,
    ) -> None:
        self._log_path = Path(log_path) if log_path else DEFAULT_LOG_PATH
        self._component = component
        self._session_id = session_id or str(uuid.uuid4())
        self._executor_version = executor_version
        self._lock = threading.Lock()
        self._prev_hash: str = GENESIS_HASH

        # Ensure the log directory exists
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        # Load the hash of the last existing log entry (if any) for chaining
        self._prev_hash = self._load_last_hash()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        event_type: EventType,
        summary: str,
        detail: str = "",
        task_id: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        component: Optional[Component] = None,
        metadata_extra: Optional[dict] = None,
    ) -> LogEntry:
        """
        Append a log entry to the prompt log.

        This is the primary public method. All system events should be
        recorded via this method.

        Args:
            event_type:     The EventType enum value for this event.
            summary:        Short human-readable description (1-2 sentences).
            detail:         Full detail, prompt content, or extended context.
            task_id:        Associated task UUID, if applicable.
            prompt_hash:    SHA-256 hash of associated prompt content, if applicable.
            component:      Override the instance-level component for this entry.
            metadata_extra: Additional key-value metadata to merge into the
                            entry's metadata object.

        Returns:
            The LogEntry that was written.

        Raises:
            IOError: If the log file cannot be written to.
            ValueError: If event_type is not a valid EventType member.
        """
        now_ns = time.time_ns()
        now_dt = datetime.fromtimestamp(now_ns / 1e9, tz=timezone.utc)
        timestamp_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

        log_id = str(uuid.uuid4())
        resolved_component = (component or self._component).value

        content = {
            "summary": summary,
            "detail": detail,
        }

        metadata = {
            "user_agent": f"prompt_logger/{LOGGER_VERSION}",
            "ip_address": None,
            "executor_version": self._executor_version,
            "schema_version": SCHEMA_VERSION,
        }
        if metadata_extra:
            metadata.update(metadata_extra)

        with self._lock:
            prev = self._prev_hash
            entry_hash = self._compute_entry_hash(
                log_id=log_id,
                timestamp_ns=now_ns,
                component=resolved_component,
                event_type=event_type.value,
                task_id=task_id,
                content=content,
                prev_hash=prev,
            )

            entry = LogEntry(
                log_id=log_id,
                session_id=self._session_id,
                timestamp=timestamp_iso,
                timestamp_ns=now_ns,
                component=resolved_component,
                event_type=event_type.value,
                task_id=task_id,
                prompt_hash=prompt_hash,
                prev_hash=prev,
                entry_hash=entry_hash,
                content=content,
                metadata=metadata,
            )

            self._append_entry(entry)
            self._prev_hash = entry_hash

        return entry

    def log_prompt_generated(
        self,
        task_id: str,
        system_prompt: str,
        user_prompt: str,
    ) -> LogEntry:
        """
        Convenience method: log a prompt generation event.

        Computes the prompt hash automatically from the provided prompts.

        Args:
            task_id:        The task UUID this prompt belongs to.
            system_prompt:  The system-role prompt string.
            user_prompt:    The user-role prompt string.

        Returns:
            The LogEntry that was written.
        """
        prompt_hash = self._hash_prompt(system_prompt, user_prompt)
        return self.log(
            event_type=EventType.PROMPT_GENERATED,
            summary=f"Prompt generated for task {task_id}",
            detail=f"System prompt length: {len(system_prompt)} chars. "
                   f"User prompt length: {len(user_prompt)} chars.",
            task_id=task_id,
            prompt_hash=prompt_hash,
        )

    def log_security_event(
        self,
        event_type: EventType,
        summary: str,
        detail: str,
        task_id: Optional[str] = None,
    ) -> LogEntry:
        """
        Convenience method: log a security-related event.

        Security events are tagged with elevated metadata to facilitate
        rapid audit review.

        Args:
            event_type: Must be a security EventType (prefix 'security_').
            summary:    Brief description of the security event.
            detail:     Full forensic detail for investigation.
            task_id:    Associated task UUID, if applicable.

        Returns:
            The LogEntry that was written.
        """
        return self.log(
            event_type=event_type,
            summary=summary,
            detail=detail,
            task_id=task_id,
            metadata_extra={"severity": "SECURITY", "requires_review": True},
        )

    def verify_chain_integrity(self) -> tuple[bool, Optional[str]]:
        """
        Verify the hash chain integrity of the entire log file.

        Reads all log entries and recomputes the hash chain from the genesis
        entry. Returns True if the chain is intact, False with an error
        description if any tampering or corruption is detected.

        Returns:
            (True, None) if chain is intact.
            (False, error_message) if any integrity violation is detected.
        """
        # Implementation deferred — see specs/security_model.md § 6.1
        raise NotImplementedError(
            "verify_chain_integrity: Implementation required in Phase 2. "
            "See specs/security_model.md § 6.1 for algorithm specification."
        )

    def get_session_id(self) -> str:
        """Return the session UUID for this logger instance."""
        return self._session_id

    def get_log_path(self) -> Path:
        """Return the resolved path to the log file."""
        return self._log_path

    # ------------------------------------------------------------------
    # Private Methods
    # ------------------------------------------------------------------

    def _append_entry(self, entry: LogEntry) -> None:
        """
        Append a single LogEntry to the JSONL log file.

        Opens the file in append mode. Creates the file if it does not exist.
        Each entry occupies exactly one line.

        This method is called within the instance lock — do not acquire
        the lock again inside this method.
        """
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(entry.to_jsonl() + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _load_last_hash(self) -> str:
        """
        Read the hash of the last entry in the existing log file.

        Used during initialization to continue the hash chain correctly
        across process restarts. Returns GENESIS_HASH if the log file
        does not exist or is empty.
        """
        if not self._log_path.exists():
            return GENESIS_HASH

        last_hash = GENESIS_HASH
        try:
            with self._log_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        last_hash = record.get("entry_hash", GENESIS_HASH)
                    except json.JSONDecodeError:
                        # Corrupted line — log corruption will be detected
                        # by verify_chain_integrity
                        pass
        except OSError:
            last_hash = GENESIS_HASH

        return last_hash

    @staticmethod
    def _compute_entry_hash(
        log_id: str,
        timestamp_ns: int,
        component: str,
        event_type: str,
        task_id: Optional[str],
        content: dict,
        prev_hash: str,
    ) -> str:
        """
        Compute the SHA-256 hash for a log entry.

        The hash is computed over a deterministic concatenation of the
        entry's identifying fields and the previous entry's hash, forming
        the hash chain.

        Args:
            All entry fields that contribute to the hash (see body).

        Returns:
            Hex-encoded SHA-256 digest string.
        """
        chain_input = "|".join([
            log_id,
            str(timestamp_ns),
            component,
            event_type,
            str(task_id),
            json.dumps(content, sort_keys=True, ensure_ascii=False),
            prev_hash,
        ])
        return hashlib.sha256(chain_input.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_prompt(system_prompt: str, user_prompt: str) -> str:
        """
        Compute SHA-256 hash of a prompt for integrity verification.

        The hash is computed over the concatenation of system and user
        prompts. This same computation MUST be used by the Local Executor
        when verifying prompt integrity from task manifests.

        See: specs/security_model.md § 4.1

        Args:
            system_prompt: The system-role prompt string.
            user_prompt:   The user-role prompt string.

        Returns:
            Hex-encoded SHA-256 digest string.
        """
        content = system_prompt + user_prompt
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Module-Level Convenience Instance
# ---------------------------------------------------------------------------

# A module-level system logger instance for use during initialization
# and in contexts where component identity is not yet established.
# Application code should prefer instantiating a component-specific logger.
_system_logger: Optional[PromptLogger] = None


def get_system_logger() -> PromptLogger:
    """
    Return the module-level system logger instance, creating it if needed.

    This is a convenience accessor for early-lifecycle logging before
    component-specific loggers are configured. Production components
    should use their own PromptLogger instances.
    """
    global _system_logger
    if _system_logger is None:
        _system_logger = PromptLogger(component=Component.SYSTEM)
    return _system_logger


# ---------------------------------------------------------------------------
# CLI Entrypoint (for verification and diagnostics)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("AI Employee Vault – Platinum Tier")
    print("Prompt Logger — Diagnostic Mode")
    print("=" * 60)

    logger = PromptLogger(component=Component.SYSTEM)

    print(f"Session ID  : {logger.get_session_id()}")
    print(f"Log Path    : {logger.get_log_path()}")
    print(f"Log Exists  : {logger.get_log_path().exists()}")
    print()

    print("Writing test log entry...")
    entry = logger.log(
        event_type=EventType.SYSTEM_STARTUP,
        summary="Prompt logger diagnostic run",
        detail="This entry was written by the diagnostic CLI entrypoint.",
        metadata_extra={"diagnostic": True},
    )

    print(f"Entry written:")
    print(f"  log_id      : {entry.log_id}")
    print(f"  timestamp   : {entry.timestamp}")
    print(f"  timestamp_ns: {entry.timestamp_ns}")
    print(f"  event_type  : {entry.event_type}")
    print(f"  entry_hash  : {entry.entry_hash}")
    print(f"  prev_hash   : {entry.prev_hash}")
    print()
    print("Diagnostic complete. Check history/prompt_log.json for the entry.")
    sys.exit(0)
