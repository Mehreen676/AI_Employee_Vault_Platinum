# AI Employee Vault – Platinum Tier Architecture V2

> **Judge-optimised architecture diagram** — Dark-themed, colorful, 7-layer flow.
> Rendered PNG: [PLATINUM_ARCHITECTURE_V2.png](PLATINUM_ARCHITECTURE_V2.png)
> Generation script: [tools/generate_architecture_v2.py](../tools/generate_architecture_v2.py)

---

## Full Architecture Diagram (Mermaid)

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {
  'primaryColor':    '#1565c0',
  'primaryTextColor':'#e3f2fd',
  'primaryBorderColor':'#64b5f6',
  'lineColor':       '#4fc3f7',
  'secondaryColor':  '#1b5e20',
  'tertiaryColor':   '#0a0e1a',
  'background':      '#0a0e1a',
  'mainBkg':         '#0d1117',
  'nodeBorder':      '#4fc3f7',
  'clusterBkg':      '#1a1a2e',
  'titleColor':      '#ffd700',
  'edgeLabelBackground':'#1a1a2e',
  'fontFamily': 'monospace'
}}}%%
flowchart TD

    classDef inputCls  fill:#1565c0,stroke:#64b5f6,color:#e3f2fd,stroke-width:2px,font-size:13px
    classDef cloudCls  fill:#2e7d32,stroke:#81c784,color:#e8f5e9,stroke-width:2px,font-size:13px
    classDef hitlCls   fill:#6a1b9a,stroke:#ce93d8,color:#f3e5f5,stroke-width:2px,font-size:13px
    classDef localCls  fill:#00695c,stroke:#80cbc4,color:#e0f2f1,stroke-width:2px,font-size:13px
    classDef toolCls   fill:#1565c0,stroke:#90caf9,color:#e3f2fd,stroke-width:1px,font-size:12px
    classDef vaultCls  fill:#d84315,stroke:#ff8a65,color:#fbe9e7,stroke-width:2px,font-size:13px
    classDef outCls    fill:#ad1457,stroke:#f48fb1,color:#fce4ec,stroke-width:2px,font-size:13px
    classDef svcCls    fill:#37474f,stroke:#90a4ae,color:#eceff1,stroke-width:2px,font-size:13px
    classDef arrowCls  fill:none,stroke:none,color:#4fc3f7,font-size:11px

    %% ═══════════════════════════════════════════════════════════
    %% LAYER 1 — INPUT
    %% ═══════════════════════════════════════════════════════════
    subgraph INPUT["📥  [ IN ]  INPUT LAYER"]
        direction LR
        GW["Gmail Watcher\ngmail_integration.py\nOAuth 2.0 + stub fallback"]
        MD["Manual Drop\nDrop .md / .json\ndirectly into vault"]
        IB["Inbox Folder\nwatcher_inbox.py\nalternate input path"]
        SL["Slack Webhook\nPOST /slack/webhook\nEvents API · intent routing"]
        WA["WhatsApp Webhook\nPOST /whatsapp/webhook\nTwilio · TwiML response"]
        VC["Voice Interface\nvoice_interface.py\nSpeechRecognition + stdin"]
        NA["Needs_Action/\nvault/Needs_Action/\nstaging queue"]
    end

    %% ═══════════════════════════════════════════════════════════
    %% LAYER 2 — CLOUD AI
    %% ═══════════════════════════════════════════════════════════
    subgraph CLOUD["☁️  [ AI ]  CLOUD AI LAYER  —  HuggingFace Spaces  (Always-On 24/7)"]
        direction LR
        CA["Cloud Agent v1.4.0\ncloud_agent/agent.py\nClaim-by-move · Daemon mode\nHeartbeat every N seconds"]
        TP["Task Planning\ntask_generator.py\nDecomposes intent\nSelects MCP tools"]
        PG["Prompt Generation\nlogging/prompt_logger.py\nSHA-256 hash chain\nAppend-only JSONL"]
        CA --> TP --> PG
    end

    %% ═══════════════════════════════════════════════════════════
    %% LAYER 3 — HITL
    %% ═══════════════════════════════════════════════════════════
    subgraph HITL["🧑‍⚖️  [ HUMAN ]  HUMAN-IN-THE-LOOP GATE"]
        direction LR
        HG["HITL Gate\nhitl.py\nInterrupts pipeline\nfor high-risk tasks"]
        HA["Human Approval\napprove.py\nMoves Pending → Approved\nOnly humans can act"]
        HR["Rejection Handling\nMoves to vault/Logs/\nTask archived with reason"]
        HG --> HA
        HG --> HR
    end

    %% ═══════════════════════════════════════════════════════════
    %% LAYER 4 — LOCAL EXECUTION
    %% ═══════════════════════════════════════════════════════════
    subgraph LOCAL["⚙️  [ RUN ]  LOCAL EXECUTION"]
        LE["Local Executor v1.3.0\nlocal_executor/executor.py\nClaim-by-move · Writes Dashboard.md\nSingle-writer rule enforced"]
        subgraph MCP["🔧  MCP TOOL LAYER  —  mcp/router.py  +  registry.py"]
            direction LR
            EM["Email MCP\nemail_mcp_stub.py"]
            CM["Calendar MCP\ncalendar_mcp_stub.py"]
            FM["File MCP\nmcp_file_ops.py"]
            SM["Social MCP\nsocial_mcp_stub.py"]
            OD["Odoo Client\nodoo_client.py\nXML-RPC draft-only"]
        end
        LE --> MCP
    end

    %% ═══════════════════════════════════════════════════════════
    %% LAYER 5 — VAULT STATE MACHINE
    %% ═══════════════════════════════════════════════════════════
    subgraph VAULT["🗄️  [ VAULT ]  VAULT STATE MACHINE  —  File-System Communication Bus"]
        direction LR
        VP["Pending_Approval/\nCloud Agent writes here\nAwaiting human review"]
        VA["Approved/\nHuman-approved tasks\nExecutor picks up here"]
        VD["Done/\nCompleted tasks\nWith execution results"]
        VR["Retry_Queue/\nFailed Odoo tasks\nno_auto_retry flag"]
        VL["Logs/\nexecution_log.json\nhealth_log.json\nrate_limit_state.json"]
    end

    %% ═══════════════════════════════════════════════════════════
    %% LAYER 6 — OUTPUT
    %% ═══════════════════════════════════════════════════════════
    subgraph OUTPUT["📤  [ OUT ]  OUTPUT & REPORTING"]
        direction LR
        EL["Execution Logs\nvault/Logs/execution_log.json\nJSONL · one record per task"]
        EP["Evidence Pack\nEvidence/JUDGE_PROOF.md\nGenerated on demand"]
        CB["CEO Report\nEvidence/CEO_REPORT.md\nPOST /reports/ceo"]
        HL["Health Logs\nvault/Logs/health_log.json\nPer-process alive/pid/restarts"]
        MT["Dashboard Metrics\nGET /metrics\ntotal · success rate · latency"]
        DL["AI Decision Log\nEvidence/AI_DECISION_LOG.md\ntool · risk · reasoning per task"]
        HR["Health Report\nEvidence/SYSTEM_HEALTH_REPORT.md\nGET /monitoring/health"]
    end

    %% ═══════════════════════════════════════════════════════════
    %% LAYER 7 — SYSTEM SERVICES
    %% ═══════════════════════════════════════════════════════════
    subgraph SVCS["🛡️  [ SVC ]  SYSTEM SERVICES"]
        direction LR
        WD["Watchdog Supervisor\nwatchdog.py\nMonitors 3 processes\nAuto-restart · health_log"]
        RL["Rate Limiter\nutils/rate_limiter.py\nemail ≤ 10/hr\nsocial ≤ 20/hr · pay ≤ 3/day"]
        RT["Retry Logic\nutils/retry.py\nExponential backoff\nDeferred queue fallback"]
        PL["Prompt Logger\nlogging/prompt_logger.py\nSHA-256 hash chain\nThread-safe Lock()"]
    end

    %% ═══════════════════════════════════════════════════════════
    %% CONNECTIONS
    %% ═══════════════════════════════════════════════════════════
    GW  -->|"atomic rename\nvault/Needs_Action/email/"| NA
    MD  --> NA
    IB  --> NA
    SL  -->|"vault task\nNeeds_Action/"| NA
    WA  -->|"vault task\nNeeds_Action/"| NA
    VC  -->|"vault task\nNeeds_Action/voice/"| NA

    NA  -->|"claim-by-move\nPath.rename()"| CA
    CA  -->|"task manifest"| VP
    CA  -->|"heartbeat feed"| VL

    VP  -->|"HITL check\nif high-risk"| HG
    HA  -->|"moves to\nApproved/"| VA
    VP  -->|"auto-approve\nlow-risk"| VA

    VA  -->|"claim-by-move\nPath.rename()"| LE
    EM  & CM & FM & SM & OD -->|"result"| LE
    LE  -->|"success"| VD
    LE  -->|"failure"| VR
    LE  -->|"JSONL record"| EL

    WD  -.->|"supervises"| CA
    WD  -.->|"supervises"| GW
    WD  -.->|"supervises"| LE
    WD  -->|"writes"| HL

    RL  -.->|"gates"| GW
    RL  -.->|"gates"| LE
    RT  -.->|"wraps"| LE
    PL  -->|"SHA-256 chain"| EP

    EL  -->|"read by"| EP
    HL  -->|"read by"| EP
    EL  -->|"read by"| CB
    EL  -->|"feeds"| MT
    LE  -->|"decision record"| DL
    WD  -->|"component status"| HR

    %% Apply styles
    class GW,MD,IB,SL,WA,VC,NA inputCls
    class CA,TP,PG cloudCls
    class HG,HA,HR hitlCls
    class LE localCls
    class EM,CM,FM,SM,OD toolCls
    class VP,VA,VD,VR,VL vaultCls
    class EL,EP,CB,HL,MT,DL,HR outCls
    class WD,RL,RT,PL svcCls
```

---

## Architecture Layer Summary

| # | Layer | Badge | Colour | Key Components |
|---|---|---|---|---|
| 1 | Input | `[IN]` | Deep Blue | Gmail, Slack Webhook, WhatsApp Webhook, Voice Interface, Manual Drop, Needs_Action Queue |
| 2 | Cloud AI | `[AI]` | Deep Green | Cloud Agent v1.4.0, Task Planning, Prompt Generation |
| 3 | Human-in-the-Loop | `[HUMAN]` | Deep Purple | HITL Gate, Human Approval, Rejection Handling |
| 4 | Local Execution | `[RUN]` | Dark Teal | Local Executor v1.3.0, MCP Tool Layer (5 tools) |
| 5 | Vault State Machine | `[VAULT]` | Deep Orange | Pending_Approval, Approved, Done, Retry_Queue, Logs |
| 6 | Output & Reporting | `[OUT]` | Deep Magenta | Execution Logs, Evidence Pack, CEO Report, Health Logs, Dashboard Metrics, AI Decision Log, Health Report |
| 7 | System Services | `[SVC]` | Dark Slate | Watchdog, Rate Limiter, Retry Logic, Prompt Logger |

---

## Claim-by-Move Protocol

```
vault/Needs_Action/email/<file>
    │  Cloud Agent: Path.rename() — atomic OS lock
    ▼
vault/In_Progress/cloud/<file>
    │  Process, generate manifest
    ▼
vault/Pending_Approval/<manifest>.json
    │  HITL gate (high-risk) → human reviews → Approved/
    │  auto-approve (low-risk)               → Approved/
    ▼
vault/Approved/<manifest>.json
    │  Local Executor: Path.rename() — atomic OS lock
    ▼
vault/In_Progress/local/<manifest>.json
    │  MCP tools execute
    ▼
vault/Done/<manifest>.json          ← success
vault/Retry_Queue/<manifest>.json   ← failure (no_auto_retry for payments)
```

**Why atomic rename?** `Path.rename()` is a single OS syscall — atomic on all POSIX
file systems. The first process to succeed owns the file. No Redis or ZooKeeper needed.

---

## Permission Boundary Matrix

| Component | Reads | Writes | External Net | Dashboard.md |
|---|---|---|---|---|
| Cloud Agent | Needs_Action/, Done/ | Pending_Approval/, In_Progress/cloud/, Updates/ | HuggingFace (inbound) | `PermissionError` |
| Gmail Integration | — | Needs_Action/email/, Deferred/email/ | Gmail API | Never |
| Slack Integration | — | Needs_Action/ | Slack Events API (inbound) | Never |
| WhatsApp Integration | — | Needs_Action/ | Twilio (inbound) | Never |
| Voice Interface | — | Needs_Action/voice/ | — (local mic / stdin) | Never |
| AI Decision Logger | — | Logs/ai_decisions.json, Evidence/AI_DECISION_LOG.md | — | Never |
| Health Monitor | Logs/heartbeat JSON files | Evidence/SYSTEM_HEALTH_REPORT.md | — | Never |
| Local Executor | Pending_Approval/, Approved/ | In_Progress/local/, Done/, Logs/, Retry_Queue/ | Odoo XML-RPC | **Only writer** |
| Watchdog | — | Logs/health_log.json | — | Never |
| Human Approver | Pending_Approval/ | Approved/ | — | — |

---

## Regenerate the PNG

```bash
# From repo root
python tools/generate_architecture_v2.py
# Output: Evidence/PLATINUM_ARCHITECTURE_V2.png  (1600 × 2700 px)
```

---

*AI Employee Vault – Platinum Tier v1.4.0 — Evidence artifact for judge verification*
