# AI Employee Vault – Platinum Tier Architecture

> **Full distributed architecture diagram** for the AI Employee Vault Platinum Tier.
> This document is the canonical visual reference for hackathon judges and auditors.

---

## System Architecture Diagram

```mermaid
flowchart TB

    classDef inputStyle    fill:#1a3a5c,stroke:#4fc3f7,color:#e3f2fd,stroke-width:2px
    classDef cloudStyle    fill:#1b3a2d,stroke:#66bb6a,color:#e8f5e9,stroke-width:2px
    classDef vaultStyle    fill:#3e2723,stroke:#ff8a65,color:#fbe9e7,stroke-width:2px
    classDef hitlStyle     fill:#311b92,stroke:#ce93d8,color:#f3e5f5,stroke-width:2px
    classDef localStyle    fill:#0d2137,stroke:#42a5f5,color:#e3f2fd,stroke-width:2px
    classDef toolsStyle    fill:#1a237e,stroke:#7986cb,color:#e8eaf6,stroke-width:2px
    classDef svcStyle      fill:#1b2a1b,stroke:#a5d6a7,color:#f1f8e9,stroke-width:2px
    classDef outputStyle   fill:#4a148c,stroke:#f48fb1,color:#fce4ec,stroke-width:2px

    %% ─────────────────────────────────────────────────────────────
    %% INPUT LAYER
    %% ─────────────────────────────────────────────────────────────
    subgraph INPUT["📥  INPUT LAYER"]
        direction TB
        GW["📧 Gmail Watcher\ngmail_watcher.py\n──────────────\nOAuth 2.0 poll\nStub fallback"]
        MD["📂 Manual Drop\nDrop .md / .json\ninto Needs_Action/"]
    end

    %% ─────────────────────────────────────────────────────────────
    %% CLOUD LAYER
    %% ─────────────────────────────────────────────────────────────
    subgraph CLOUD["☁️  CLOUD LAYER  (HuggingFace Spaces — Always-On 24/7)"]
        direction TB
        CA["🤖 Cloud Agent v1.4.0\ncloud_agent/agent.py\n──────────────────────\nClaim-by-move protocol\nDaemon + auto mode\nHeartbeat every N sec"]
        TP["🧠 Task Planning\ntask_generator.py\n─────────────────\nDecomposes email intent\nSelects MCP tools\nBuilds manifest JSON"]
        PG["✍️ Prompt Generation\nprompt_logger.py\n─────────────────\nSHA-256 hash chain\nAppend-only JSONL\nNanosecond timestamps"]
    end

    %% ─────────────────────────────────────────────────────────────
    %% VAULT STATE MACHINE
    %% ─────────────────────────────────────────────────────────────
    subgraph VAULT["🗄️  VAULT STATE MACHINE  (File-System Communication Bus)"]
        direction LR
        NA["📋 Needs_Action/\n+ email/"]
        IP_C["⚙️ In_Progress/\ncloud/"]
        PA["📬 Pending_\nApproval/"]
        AP["✅ Approved/"]
        IP_L["⚙️ In_Progress/\nlocal/"]
        DN["✔️ Done/"]
        RQ["🔄 Retry_Queue/"]
        LG["📊 Logs/\nexecution_log.json\nhealth_log.json\nrate_limit_state.json"]
        UD["📡 Updates/\ncloud_updates.md"]
        DF["⏳ Deferred/\nemail/"]

        NA --> IP_C
        IP_C --> PA
        PA --> AP
        AP --> IP_L
        IP_L --> DN
        IP_L --> RQ
        IP_L --> LG
    end

    %% ─────────────────────────────────────────────────────────────
    %% HITL LAYER
    %% ─────────────────────────────────────────────────────────────
    subgraph HITL["👤  HITL LAYER  (Human-In-The-Loop Gate)"]
        direction TB
        HG["🚧 HITL Gate\nhitl.py\n──────────────\nInterrupts pipeline\nfor high-risk tasks\nBlocks until reviewed"]
        HA["✅ Human Approval\napprove.py\n──────────────\nInspects manifest\nMoves to Approved/\nOnly humans can do this"]
    end

    %% ─────────────────────────────────────────────────────────────
    %% LOCAL EXECUTION
    %% ─────────────────────────────────────────────────────────────
    subgraph LOCAL["💻  LOCAL EXECUTION  (On-Premise)"]
        direction TB
        LE["⚙️ Local Executor v1.3.0\nlocal_executor/executor.py\n────────────────────────────\nClaim-by-move from Approved/\nWrites Dashboard.md\nSingle-writer rule enforced"]
        MT["🔧 MCP Tool Layer\nmcp/router.py  +  registry.py\n───────────────────────────\nDispatches to correct MCP stub\nEmail / Calendar / Social / Odoo"]
    end

    %% ─────────────────────────────────────────────────────────────
    %% MCP TOOLS
    %% ─────────────────────────────────────────────────────────────
    subgraph TOOLS["🛠️  MCP TOOL LAYER"]
        direction TB
        EM["📧 Email MCP\nemail_mcp_stub.py"]
        CM["📅 Calendar MCP\ncalendar_mcp_stub.py"]
        FM["📁 File MCP\nmcp_file_ops.py"]
        SM["📱 Social MCP\nsocial_mcp_stub.py"]
        OD["🏢 Odoo Client\nodoo_client.py\nXML-RPC draft-only"]
    end

    %% ─────────────────────────────────────────────────────────────
    %% SYSTEM SERVICES
    %% ─────────────────────────────────────────────────────────────
    subgraph SERVICES["⚙️  SYSTEM SERVICES"]
        direction TB
        WD["🐕 Watchdog Supervisor\nwatchdog.py\n────────────────\nMonitors all 3 procs\nAuto-restart on exit\nWrites health_log.json"]
        RL["⏱️ Rate Limiter\nutils/rate_limiter.py\n─────────────────────\nemail ≤ 10/hr\nsocial ≤ 20/hr\npayment ≤ 3/day"]
        RT["🔁 Retry Logic\nutils/retry.py\n──────────────────\nExponential backoff\nPayment: no_auto_retry\nDeferred queue fallback"]
        PL["📝 Prompt Logger\nlogging/prompt_logger.py\n────────────────────────\nSHA-256 chain integrity\nThread-safe Lock()\nAppend-only JSONL"]
    end

    %% ─────────────────────────────────────────────────────────────
    %% OUTPUT LAYER
    %% ─────────────────────────────────────────────────────────────
    subgraph OUTPUT["📤  OUTPUT LAYER"]
        direction TB
        EL["📋 Execution Logs\nvault/Logs/\nexecution_log.json"]
        EP["🔍 Evidence Pack\nEvidence/JUDGE_PROOF.md\nGenerated on demand"]
        CB["📊 CEO Briefing\nBriefings/YYYY-MM-DD.md\nDaily 07:00 UTC"]
        HL["💚 Health Logs\nvault/Logs/health_log.json\nPer-process alive/pid/restarts"]
    end

    %% ─────────────────────────────────────────────────────────────
    %% CONNECTIONS BETWEEN LAYERS
    %% ─────────────────────────────────────────────────────────────
    GW  -->|"writes email_*.md\natomic rename"| NA
    MD  -->|"drops manifest\nor task file"| NA

    NA  -->|"claim-by-move\nPath.rename()"| CA
    CA  --> TP
    TP  --> PG
    CA  -->|"writes task manifest\nto Pending_Approval/"| PA
    CA  -->|"heartbeat feed"| UD

    PA  -->|"HITL check\nif high-risk"| HG
    HG  -->|"blocks until\nhuman acts"| HA
    HA  -->|"moves file\nto Approved/"| AP
    PA  -->|"direct approve\nfor low-risk tasks"| AP

    AP  -->|"claim-by-move\nPath.rename()"| LE
    LE  --> MT
    MT  --> EM
    MT  --> CM
    MT  --> FM
    MT  --> SM
    MT  --> OD

    LE  -->|"completed task"| DN
    LE  -->|"failure → retry"| RQ
    LE  -->|"writes"| EL

    WD  -.->|"supervises"| CA
    WD  -.->|"supervises"| GW
    WD  -.->|"supervises"| LE
    WD  -->|"writes"| HL

    RL  -.->|"gates"| GW
    RL  -.->|"gates"| LE
    RT  -.->|"wraps"| LE

    EL  -->|"read by"| EP
    HL  -->|"read by"| EP
    PL  -->|"audit chain\nread by"| EP
    EL  -->|"read by"| CB

    %% Apply styles
    class GW,MD inputStyle
    class CA,TP,PG cloudStyle
    class NA,IP_C,PA,AP,IP_L,DN,RQ,LG,UD,DF vaultStyle
    class HG,HA hitlStyle
    class LE,MT localStyle
    class EM,CM,FM,SM,OD toolsStyle
    class WD,RL,RT,PL svcStyle
    class EL,EP,CB,HL outputStyle
```

---

## Architecture Layer Summary

| Layer | Components | Technology |
|---|---|---|
| **Input** | Gmail Watcher, Manual Drop | Python, Gmail OAuth 2.0, atomic rename |
| **Cloud** | Cloud Agent v1.4.0, Task Planner, Prompt Logger | Python, HuggingFace Spaces, SHA-256 |
| **Vault** | 10-directory state machine | File system, `Path.rename()` distributed lock |
| **HITL** | hitl.py, approve.py | Human-in-the-loop gate |
| **Local Exec** | Local Executor v1.3.0, MCP Router | Python, XML-RPC, importlib |
| **MCP Tools** | Email, Calendar, File, Social, Odoo | Stub layer + real Odoo XML-RPC |
| **Services** | Watchdog, Rate Limiter, Retry, Logger | threading.Lock, JSONL, exponential backoff |
| **Output** | Execution Logs, Evidence Pack, CEO Briefing | Markdown, JSONL, SHA-256 chain |

---

## Claim-by-Move Protocol (Distributed Lock)

```
Needs_Action/<file>
    │
    │  Cloud Agent: Path.rename() — atomic OS-level lock
    ▼
In_Progress/cloud/<file>
    │
    │  Cloud Agent processes, generates manifest
    ▼
Pending_Approval/<manifest>.json
    │
    │  (HITL gate if high-risk)  →  Human reviews  →  Approved/
    │  (auto-approve low-risk)   →  Approved/
    ▼
Approved/<manifest>.json
    │
    │  Local Executor: Path.rename() — atomic OS-level lock
    ▼
In_Progress/local/<manifest>.json
    │
    │  Local Executor calls MCP tools
    ▼
Done/<manifest>.json  (success)
Retry_Queue/<manifest>.json  (failure, payment tasks: no_auto_retry)
```

**Why atomic rename?** `os.rename()` / `Path.rename()` is guaranteed atomic on
POSIX file systems (single-syscall). The first process to call rename "wins" —
no second process can claim the same file. This eliminates the need for a
distributed lock service (Redis, ZooKeeper, etcd) while preserving all
concurrency guarantees.

---

## Data Flow — Single Task End-to-End

```
[Gmail]  →  email_001.md  →  vault/Needs_Action/email/
                                        │ Cloud Agent claims
                                        ▼
                              vault/In_Progress/cloud/email_001.md
                                        │ generate manifest
                                        ▼
                              vault/Pending_Approval/task_abc.json
                                        │ HITL gate (if needed)
                                        ▼
                                    Human reviews
                                        │ approve
                                        ▼
                              vault/Approved/task_abc.json
                                        │ Local Executor claims
                                        ▼
                              vault/In_Progress/local/task_abc.json
                                        │ MCP tool executes
                                        ▼
                              vault/Done/task_abc.json
                                        │
                              history/prompt_log.json  (SHA-256 chain entry)
                              vault/Logs/execution_log.json  (JSONL record)
```

---

## Permission Boundary Matrix

| Component | Can Read | Can Write | External Net | Dashboard.md |
|---|---|---|---|---|
| Cloud Agent | Needs_Action/, Done/ | Pending_Approval/, In_Progress/cloud/, Updates/ | HuggingFace (inbound) | ❌ PermissionError |
| Gmail Watcher | — | Needs_Action/email/, Deferred/email/ | Gmail API | ❌ Never |
| Local Executor | Pending_Approval/, Approved/ | In_Progress/local/, Done/, Logs/, Retry_Queue/ | Odoo XML-RPC | ✅ Only writer |
| Watchdog | — | Logs/health_log.json | — | ❌ Never |
| Human Approver | Pending_Approval/ | Approved/ | — | — |

---

*Generated for AI Employee Vault – Platinum Tier v1.4.0*
*Evidence artifact — for judge verification and system audit*
