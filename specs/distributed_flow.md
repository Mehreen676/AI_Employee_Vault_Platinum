# AI Employee Vault – Platinum Tier: Distributed Workflow Specification

**Document Version:** 1.0.0
**Classification:** Internal Engineering Reference
**Last Updated:** 2026-02-27
**Status:** Authoritative

---

## 1. Overview

This document provides a complete, step-by-step specification of the distributed workflow that governs task lifecycle management in the Platinum Tier system. Every task processed by this system must follow this workflow exactly. Deviations require explicit override documentation and are subject to audit review.

---

## 2. Actors

| Actor | Type | Location | Role |
|---|---|---|---|
| **User / Client** | Human or API caller | Remote / browser | Initiates task requests |
| **Cloud Agent** | Software process | HuggingFace Spaces | Plans, reasons, generates prompts |
| **Human Approver** | Human | Local machine | Reviews and approves pending tasks |
| **Local Executor** | Software process | Local machine | Executes approved tasks |
| **Vault** | File system | Shared (synced) folder | State persistence and communication bus |
| **Prompt Logger** | Software library | Both components | Records all activity |

---

## 3. Complete Distributed Workflow

### Phase 1: Task Ingestion (Cloud Agent)

```
Step 1.1 — CLIENT REQUEST
─────────────────────────
Actor: User/Client
Action: Submits task specification to Cloud Agent via API or UI
Artifact: Raw task request (text, structured JSON, or form input)
Logged: YES — event_type: "task_received"

Step 1.2 — TASK DECOMPOSITION
──────────────────────────────
Actor: Cloud Agent
Action: Analyzes task request, decomposes into atomic subtasks if required,
        determines task_type, priority, and required parameters
Artifact: Internal task plan (in-memory)
Logged: YES — event_type: "task_decomposed"

Step 1.3 — PROMPT GENERATION
─────────────────────────────
Actor: Cloud Agent
Action: Generates structured prompt for task execution. Prompt includes
        system instructions, user context, and execution parameters.
        Computes SHA-256 hash of prompt content.
Artifact: Prompt object with hash
Logged: YES — event_type: "prompt_generated"

Step 1.4 — MANIFEST CREATION
─────────────────────────────
Actor: Cloud Agent
Action: Assembles complete task manifest conforming to platinum_design.md schema.
        Assigns UUID task_id, sets status="pending_approval".
        Writes manifest to vault/Pending_Approval/ using naming convention.
Artifact: {PRIORITY}-{TIMESTAMP}-{TASK_ID_SHORT}.json in vault/Pending_Approval/
Logged: YES — event_type: "task_submitted"
```

### Phase 2: Human Approval Gate

```
Step 2.1 — NOTIFICATION (Optional)
────────────────────────────────────
Actor: Cloud Agent (async)
Action: Notifies designated approver(s) that a task awaits review.
        Notification may be email, Slack webhook, or polling dashboard.
Artifact: Notification event
Logged: YES — event_type: "approval_notification_sent"

Step 2.2 — HUMAN REVIEW
─────────────────────────
Actor: Human Approver
Action: Reads task manifest from vault/Pending_Approval/.
        Reviews: task_type, description, prompt content, parameters, priority.
        Makes APPROVE or REJECT decision.
Artifact: Decision (mental/physical)
Logged: Pending until action (Step 2.3 or 2.4)

Step 2.3 — APPROVAL PATH
──────────────────────────
Actor: Human Approver
Action: Updates manifest: sets status="approved", approval.approved_by=approver_id,
        approval.approved_at=timestamp, appends audit log entry.
        Moves manifest file from vault/Pending_Approval/ to vault/Approved/
        (atomic rename operation — must not copy).
Artifact: Manifest in vault/Approved/
Logged: YES — event_type: "task_approved"

Step 2.4 — REJECTION PATH
───────────────────────────
Actor: Human Approver
Action: Updates manifest: sets status="rejected", records rejection reason.
        Moves manifest from vault/Pending_Approval/ to vault/Logs/.
Artifact: Manifest in vault/Logs/ with rejection record
Logged: YES — event_type: "task_rejected"
Workflow: TERMINATES for this task

Step 2.5 — EXPIRATION PATH
────────────────────────────
Actor: Cloud Agent (scheduled check)
Action: If task remains in vault/Pending_Approval/ beyond APPROVAL_TIMEOUT_HOURS,
        Cloud Agent marks task as expired, moves to vault/Logs/.
Artifact: Manifest in vault/Logs/ with expiration record
Logged: YES — event_type: "task_expired"
Workflow: TERMINATES for this task
```

### Phase 3: Local Execution

```
Step 3.1 — VAULT POLLING
──────────────────────────
Actor: Local Executor
Action: Monitors vault/Approved/ directory at configured poll interval (default: 5s).
        Detects newly appeared manifest files.
Artifact: File system event
Logged: NO (polling is silent; only logged if task detected)

Step 3.2 — PRE-EXECUTION VALIDATION
──────────────────────────────────────
Actor: Local Executor
Action: Reads and validates manifest against platinum_design.md schema.
        Verifies prompt hash integrity (SHA-256 recomputation).
        Checks task_id uniqueness against execution history.
        Validates all required parameters are present.
Result: PASS → proceed to Step 3.3 | FAIL → Step 3.2a

Step 3.2a — VALIDATION FAILURE
─────────────────────────────────
Actor: Local Executor
Action: Logs validation failure with detailed error report.
        Moves manifest to vault/Logs/ with status="validation_failed".
Logged: YES — event_type: "task_validation_failed"
Workflow: TERMINATES for this task

Step 3.3 — EXECUTION LOCK ACQUISITION
───────────────────────────────────────
Actor: Local Executor
Action: Acquires execution lock for task_id (prevents double-execution).
        Updates manifest: status="executing", execution.started_at=now,
        execution.executor_id=this_executor_id. Writes updated manifest back.
Artifact: Lock file in vault/Approved/ (e.g., {task_id}.lock)
Logged: YES — event_type: "task_execution_started"

Step 3.4 — TASK EXECUTION
───────────────────────────
Actor: Local Executor
Action: Executes task in accordance with task_type handler.
        Captures stdout, stderr, and exit code.
        Enforces execution timeout (configurable per task_type).
Artifact: Execution result (in-memory)
Logged: YES — event_type: "task_executing" (periodic heartbeat if long-running)

Step 3.5 — RESULT CAPTURE (SUCCESS)
──────────────────────────────────────
Actor: Local Executor
Action: Updates manifest with execution results:
        execution.completed_at, execution.exit_code, execution.stdout, execution.stderr.
        Sets status="done". Appends final audit log entry.
        Moves manifest from vault/Approved/ to vault/Done/ (atomic rename).
        Releases execution lock.
Artifact: Completed manifest in vault/Done/
Logged: YES — event_type: "task_completed"

Step 3.5a — RESULT CAPTURE (FAILURE)
───────────────────────────────────────
Actor: Local Executor
Action: Captures error information. Updates manifest with failure details.
        Sets status="failed". Appends failure audit log entry.
        Moves manifest from vault/Approved/ to vault/Logs/ (atomic rename).
        Releases execution lock.
Artifact: Failed manifest in vault/Logs/
Logged: YES — event_type: "task_failed"
```

### Phase 4: Result Retrieval (Cloud Agent)

```
Step 4.1 — RESULT POLLING
───────────────────────────
Actor: Cloud Agent
Action: Monitors vault/Done/ for manifests with matching task_ids.
        Detects completed tasks and reads result manifests.
Artifact: Completed manifest (read)
Logged: YES — event_type: "task_result_retrieved"

Step 4.2 — RESULT PROCESSING
──────────────────────────────
Actor: Cloud Agent
Action: Processes execution results. May generate follow-up tasks if
        task was part of a multi-step workflow.
Artifact: Processed result, optional follow-up task request
Logged: YES — event_type: "result_processed"

Step 4.3 — CLIENT RESPONSE
────────────────────────────
Actor: Cloud Agent
Action: Returns task result to original requesting client via API response
        or async notification.
Artifact: API response or webhook payload
Logged: YES — event_type: "client_response_sent"
```

---

## 4. Sequence Diagram

```
USER         CLOUD AGENT      VAULT/Pending    APPROVER      VAULT/Approved   LOCAL EXEC    VAULT/Done
 │                │                │               │                │               │              │
 │──submit task──►│                │               │                │               │              │
 │                │──plan/prompt──►│               │                │               │              │
 │                │                │──notify───────►               │               │              │
 │                │                │               │─review─────────────────────────────────────  │
 │                │                │               │──approve──────►│               │              │
 │                │                │               │                │◄──poll────────│              │
 │                │                │               │                │──validate─────►              │
 │                │                │               │                │──execute──────►              │
 │                │                │               │                │               │──write done─►│
 │◄─result────────│◄───────────────────────────────────────────────────────────────────────────────│
 │                │                │               │                │               │              │
```

---

## 5. Concurrency and Race Condition Handling

### 5.1 Multi-Executor Deployments

When multiple Local Executor instances share a single Vault, the following rules apply:

- **File Claim:** The first executor to successfully rename (atomic) a file from `Approved/` to a working-copy path wins the task. All others will find the file gone and skip it.
- **Lock Files:** Each executor writes a `.lock` file alongside claimed tasks. If a `.lock` file is present without a corresponding task manifest, it indicates an executor crash — the orphaned lock is cleaned up after `LOCK_TIMEOUT_SECONDS`.

### 5.2 Cloud Agent Write Conflicts

Multiple Cloud Agent instances (if deployed) write to `Pending_Approval/` using UUIDs in filenames, ensuring no naming collisions.

### 5.3 Approval Race Conditions

If two approvers simultaneously attempt to approve/reject the same task, the first atomic rename wins. The second will fail (file not found) and receive an appropriate error — preventing double-approval or conflicting decisions.

---

## 6. Failure Recovery Procedures

| Failure Scenario | Detection Method | Recovery Action |
|---|---|---|
| Local Executor crash mid-execution | Lock file without active process | Resume or re-queue task after lock timeout |
| Vault sync interruption | Manifest not appearing in Approved/ | Cloud Agent retries after timeout; alerts operator |
| Cloud Agent restart | HuggingFace Space restart policy | Pending tasks remain in Vault; no data loss |
| Corrupted manifest | Schema validation failure | Task moved to vault/Logs/ with corruption report |
| Network partition | Vault sync failure | Tasks queue in local Pending_Approval; sync on reconnect |
| Approval timeout | Cloud Agent scheduled check | Task expired, logged, requester notified |

---

## 7. Monitoring Checkpoints

The following events serve as monitoring checkpoints for operational health:

1. **Task Age in Pending_Approval** — Alert if > `APPROVAL_TIMEOUT_HOURS * 0.8`
2. **Vault/Approved queue depth** — Alert if > 10 tasks (potential executor bottleneck)
3. **Execution duration** — Alert if task exceeds configured timeout * 0.9
4. **Failed task rate** — Alert if failure rate > 5% over rolling 1-hour window
5. **Log write failures** — Critical alert — logging subsystem health is non-negotiable
6. **Lock file orphan detection** — Warning if lock file age > `LOCK_TIMEOUT_SECONDS * 2`

---

*End of Distributed Flow Specification — AI Employee Vault Platinum Tier v1.0.0*
