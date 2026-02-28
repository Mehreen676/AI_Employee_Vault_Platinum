# AI Employee Vault – Platinum Tier: Design Specification

**Document Version:** 1.0.0
**Classification:** Internal Engineering Reference
**Last Updated:** 2026-02-27
**Status:** Authoritative

---

## 1. Purpose

This document defines the Platinum Tier design philosophy, component interface contracts, data schemas, and operational requirements. It serves as the implementation contract for all engineers contributing to this system. No implementation decision that contradicts this specification is valid without a formal spec amendment.

---

## 2. Platinum Tier Differentiators

The Platinum Tier represents the highest operational tier of the AI Employee Vault system. It distinguishes itself from lower tiers through the following capabilities:

| Capability | Silver | Gold | Platinum |
|---|---|---|---|
| Cloud Agent Deployment | No | Yes (shared) | Yes (dedicated) |
| Local Executor | No | No | Yes |
| Approval Workflow | No | Manual | Structured Vault-based |
| Prompt Logging | Basic | Standard | Immutable JSONL with hashing |
| Audit Trail | No | Partial | Full end-to-end |
| Spec-Driven Dev | Recommended | Required | Mandatory |
| Judge-Proof Docs | No | Partial | Full |
| Vault State Machine | No | No | Yes |
| Multi-Machine Support | No | No | Yes (via Vault sync) |

---

## 3. Component Interface Contracts

### 3.1 Task Manifest Schema

Every task written to the Vault must conform to the following JSON schema. This is the binding contract between the Cloud Agent (writer) and the Local Executor (reader).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12",
  "type": "object",
  "required": [
    "task_id",
    "version",
    "created_at",
    "created_by",
    "status",
    "priority",
    "task_type",
    "description",
    "prompt",
    "parameters",
    "approval",
    "audit"
  ],
  "properties": {
    "task_id": {
      "type": "string",
      "description": "UUID v4 unique task identifier",
      "example": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    },
    "version": {
      "type": "string",
      "description": "Task manifest schema version",
      "example": "1.0.0"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 UTC timestamp of task creation"
    },
    "created_by": {
      "type": "string",
      "description": "Identifier of the Cloud Agent instance or user that created this task"
    },
    "status": {
      "type": "string",
      "enum": ["pending_approval", "approved", "rejected", "executing", "done", "failed"],
      "description": "Current task lifecycle state"
    },
    "priority": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10,
      "description": "Task priority: 1 (lowest) to 10 (critical)"
    },
    "task_type": {
      "type": "string",
      "description": "Categorical task classification (e.g., 'code_generation', 'data_analysis')"
    },
    "description": {
      "type": "string",
      "description": "Human-readable task description for approver review"
    },
    "prompt": {
      "type": "object",
      "description": "The full prompt artifact",
      "required": ["system", "user", "hash"],
      "properties": {
        "system": { "type": "string" },
        "user": { "type": "string" },
        "hash": { "type": "string", "description": "SHA-256 of prompt content for integrity verification" }
      }
    },
    "parameters": {
      "type": "object",
      "description": "Task-specific execution parameters"
    },
    "approval": {
      "type": "object",
      "properties": {
        "required": { "type": "boolean" },
        "approved_by": { "type": ["string", "null"] },
        "approved_at": { "type": ["string", "null"], "format": "date-time" },
        "notes": { "type": ["string", "null"] }
      }
    },
    "execution": {
      "type": "object",
      "description": "Populated by Local Executor upon completion",
      "properties": {
        "started_at": { "type": ["string", "null"] },
        "completed_at": { "type": ["string", "null"] },
        "executor_id": { "type": ["string", "null"] },
        "exit_code": { "type": ["integer", "null"] },
        "stdout": { "type": ["string", "null"] },
        "stderr": { "type": ["string", "null"] }
      }
    },
    "audit": {
      "type": "object",
      "required": ["log_entries"],
      "properties": {
        "log_entries": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["timestamp", "actor", "action"],
            "properties": {
              "timestamp": { "type": "string" },
              "actor": { "type": "string" },
              "action": { "type": "string" },
              "detail": { "type": "string" }
            }
          }
        }
      }
    }
  }
}
```

### 3.2 Cloud Agent API Contract

The Cloud Agent exposes the following internal interface (implementation details deferred to `cloud_agent/` module specs):

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness probe — returns system status |
| `/tasks/submit` | POST | Submit a new task to the Vault queue |
| `/tasks/{task_id}` | GET | Retrieve task status by ID |
| `/tasks/pending` | GET | List all tasks in `Pending_Approval/` |
| `/tasks/done` | GET | List all completed tasks |
| `/logs/recent` | GET | Retrieve recent prompt log entries |

### 3.3 Local Executor CLI Contract

The Local Executor exposes the following command-line interface:

```
Usage: python -m local_executor [COMMAND] [OPTIONS]

Commands:
  watch       Begin watching vault/Approved/ for tasks to execute
  execute     Manually execute a specific task by task_id
  status      Show current executor status and active tasks
  history     Show execution history from vault/Done/
  validate    Validate a task manifest without executing it

Options:
  --vault-path PATH     Path to the shared Vault directory
  --concurrency INT     Maximum concurrent task executions (default: 1)
  --dry-run             Execute validation only, no side effects
  --log-level LEVEL     Logging verbosity (DEBUG/INFO/WARNING/ERROR)
```

---

## 4. Vault Directory Conventions

### 4.1 File Naming Convention

Task manifest files follow a strict naming convention to enable sorting, filtering, and collision avoidance:

```
{PRIORITY}-{TIMESTAMP}-{TASK_ID_SHORT}.json

Example:
  05-20260227T143022Z-f47ac10b.json
```

### 4.2 Directory Semantics

| Directory | Contents | Writer | Reader |
|---|---|---|---|
| `vault/Pending_Approval/` | Task manifests awaiting human review | Cloud Agent | Human approver |
| `vault/Approved/` | Manifests approved for execution | Human approver | Local Executor |
| `vault/Done/` | Completed task manifests with results | Local Executor | Cloud Agent, human |
| `vault/Logs/` | Rejected tasks, failed tasks, system events | All components | Auditors |

### 4.3 Transition Protocol

State transitions are performed by **moving** files between directories, never by copying. This ensures atomicity and prevents duplicate execution. The move operation must be atomic (rename-based) to prevent race conditions.

---

## 5. Logging Design

### 5.1 Prompt Log Entry Format

```json
{
  "log_id": "uuid-v4",
  "session_id": "uuid-v4",
  "timestamp": "ISO-8601-UTC",
  "timestamp_ns": 1234567890123456789,
  "component": "cloud_agent | local_executor | human",
  "event_type": "prompt_generated | task_submitted | task_approved | task_executed | task_failed",
  "task_id": "uuid-v4 or null",
  "prompt_hash": "sha256-hex",
  "content": {
    "summary": "Human-readable event summary",
    "detail": "Full event detail or prompt content"
  },
  "metadata": {
    "user_agent": "string",
    "ip_address": "string or null",
    "executor_version": "string"
  }
}
```

### 5.2 Log Rotation Policy

- Primary log: `history/prompt_log.json` (JSONL format, one JSON object per line)
- Rotation: When log exceeds 10MB, rotate to `history/prompt_log.{DATE}.json`
- Retention: Minimum 90 days (configurable)
- Compression: Rotated logs compressed with gzip

---

## 6. Configuration Management

All system configuration is managed through environment variables and optional `.env` files. No secrets are stored in the Vault or version-controlled files.

| Variable | Component | Description | Default |
|---|---|---|---|
| `VAULT_PATH` | Both | Absolute path to shared Vault directory | `./vault` |
| `CLOUD_AGENT_URL` | Local Executor | URL of Cloud Agent API | Required |
| `EXECUTOR_ID` | Local Executor | Unique identifier for this executor instance | Auto-generated UUID |
| `EXECUTOR_CONCURRENCY` | Local Executor | Max concurrent tasks | `1` |
| `LOG_LEVEL` | Both | Logging verbosity | `INFO` |
| `PROMPT_LOG_PATH` | Both | Path to prompt log file | `./history/prompt_log.json` |
| `HF_TOKEN` | Cloud Agent | HuggingFace API token | Required for deployment |
| `APPROVAL_TIMEOUT_HOURS` | Cloud Agent | Hours before pending task expires | `24` |

---

## 7. Error Handling Philosophy

- **Cloud Agent errors:** Logged to prompt log, task status set to `failed`, no silent failures.
- **Local Executor errors:** Captured in task manifest's `execution.stderr`, task moved to `vault/Logs/`, alert generated.
- **Vault access errors:** Treated as critical — executor pauses and logs until resolved.
- **Schema validation errors:** Task rejected with detailed validation report written to `vault/Logs/`.

---

## 8. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Cloud Agent uptime | 99.5% (HuggingFace Spaces SLA) |
| Task manifest write latency | < 500ms |
| Local Executor poll interval | 5 seconds (configurable) |
| Log write latency | < 10ms per entry |
| Vault file operation atomicity | Guaranteed via atomic rename |
| Maximum task manifest size | 1MB |
| Supported OS (Local Executor) | Linux, macOS, Windows 10+ |

---

*End of Platinum Design Specification — AI Employee Vault Platinum Tier v1.0.0*
