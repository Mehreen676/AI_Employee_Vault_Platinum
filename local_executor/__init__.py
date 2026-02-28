"""
AI Employee Vault – Platinum Tier
Local Executor Module

Module:   local_executor/__init__.py
Version:  1.0.0
Status:   Active — Phase 2 Implemented

Description:
    The Local Executor runs on the user's local machine. It monitors the
    vault/Approved/ directory for task manifests that have cleared the
    human approval gate, validates them, executes them in an isolated
    environment, and writes results to vault/Done/.

    Responsibilities:
        - Poll or watch vault/Approved/ for executable task manifests
        - Enforce pre-execution schema validation (platinum_design.md § 3.1)
        - Verify prompt SHA-256 hash integrity before execution
        - Enforce task_id uniqueness (prevent replay attacks)
        - Execute tasks in isolated subprocesses with resource limits
        - Capture stdout, stderr, and exit codes
        - Write completed task manifests to vault/Done/ (atomic rename)
        - Write failed task manifests to vault/Logs/ (atomic rename)
        - Log all execution events via logging.prompt_logger.PromptLogger
        - Manage execution lock files to prevent double-execution

    This module does NOT originate tasks. Task creation is exclusively the
    domain of the cloud_agent module.

Specification Reference:
    specs/architecture.md § 4.2
    specs/platinum_design.md § 3.3 (CLI contract)
    specs/distributed_flow.md § Phase 3
    specs/security_model.md § 3.1, § 5

Implementation Notes:
    - VAULT_PATH env var controls Vault directory location
    - EXECUTOR_ID env var (or auto UUID) identifies this executor instance
    - EXECUTOR_CONCURRENCY env var controls max parallel task execution
    - All file transitions MUST use atomic rename (not copy)
    - Execution sandboxing level: see specs/security_model.md § 5.1
    - Lock file convention: vault/Approved/{task_id}.lock

Phase 2 Implementation Checklist:
    [ ] Implement Vault watcher / polling loop
    [ ] Implement manifest schema validator
    [ ] Implement prompt hash verifier
    [ ] Implement task_id deduplication registry
    [ ] Implement execution lock manager
    [ ] Implement task runner (subprocess, timeout enforcement)
    [ ] Implement result capture and manifest updater
    [ ] Implement atomic Vault state transitions
    [ ] Integrate PromptLogger into all execution lifecycle events
    [ ] Implement CLI interface per specs/platinum_design.md § 3.3
    [ ] Write unit tests for all components
    [ ] Write integration tests against Vault
    [ ] Document sandboxing configuration for target OS
"""

__version__ = "1.0.0"
__status__ = "active"
__component__ = "local_executor"

def __getattr__(name: str):
    # Lazy import prevents RuntimeWarning when running
    # `python -m local_executor.executor` while the package __init__
    # is loaded before the submodule finishes initialising.
    if name == "LocalExecutor":
        from .executor import LocalExecutor  # noqa: PLC0415
        return LocalExecutor
    raise AttributeError(f"module 'local_executor' has no attribute {name!r}")

__all__ = ["LocalExecutor"]
