# AI Employee Vault - Platinum Tier
## Run Checklist (Local + Cloud + Verification)

This checklist reflects enforced HITL gating:

`Needs_Action -> Waiting_Approval -> (approve.py) -> Pending_Approval -> Done`

---

## A) Local Run (Windows / PowerShell)

### 1) Setup
```powershell
cd "C:\Users\Zohair\Desktop\HACKTHONE 0 MEHREEN\AI_Employee_Vault_Platinum"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Start watcher (optional live Gmail feed)
```powershell
python -m watchers.gmail_watcher --daemon --interval 30
```

### 3) Start Cloud Agent (writes to Waiting_Approval)
```powershell
python cloud_agent.py --daemon --auto --interval 5
```

### 4) Review and approve tasks (HITL gate)
```powershell
python approve.py list
python approve.py status
python approve.py approve task_<uuid>.json
# optional reject:
python approve.py reject task_<uuid>.json "not acceptable"
```

### 5) Start Local Executor (consumes ONLY Pending_Approval)
```powershell
python local_executor.py --poll 2
```

### 6) Generate evidence pack
```powershell
python scripts/generate_evidence_pack.py --n 20
```

Output:
- `Evidence/JUDGE_PROOF.md`

---

## B) Cloud Run (Ubuntu VM)

### 1) Setup
```bash
cd /home/ubuntu/AI_Employee_Vault_Platinum
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Start Cloud Agent
```bash
python3 cloud_agent.py --daemon --auto --interval 5
```

### 3) Human approval (same repo/vault)
```bash
python3 approve.py list
python3 approve.py status
python3 approve.py approve task_<uuid>.json
# optional reject:
python3 approve.py reject task_<uuid>.json "not acceptable"
```

### 4) Start Local Executor
```bash
python3 local_executor.py --poll 2
```

### 5) Optional single-entrypoint watchdog
```bash
python3 watchdog.py --start-all --interval 10
```

---

## C) Verification Commands

### 1) Verify expected folder moves
```bash
# Before approval: files appear here
ls vault/Waiting_Approval/

# After approve.py: files move here
ls vault/Pending_Approval/

# During execution claim:
ls vault/In_Progress/local/

# Final destination:
ls vault/Done/
```

Expected movement:
1. `vault/Needs_Action/email/*.md`
2. `vault/In_Progress/cloud/*` (claim-by-move)
3. `vault/Waiting_Approval/task_*.json`
4. `vault/Pending_Approval/task_*.json` (via `approve.py`)
5. `vault/In_Progress/local/task_*.json` (claim-by-move)
6. `vault/Done/task_*.json`

### 2) Verify logs
```bash
# Task execution transitions
cat vault/Logs/execution_log.json

# Process liveness / restarts (if watchdog used)
cat vault/Logs/health_log.json

# Human approvals audit trail
cat vault/Logs/approval_log.json

# Prompt/event hash-chained history
cat history/prompt_log.json
```

### 3) Verify prompt history chain integrity
```bash
python tools/verify_history_chain.py
```

Expected:
- `PASS: chain valid (<N> lines)`

### 4) Verify MCP proof output
```bash
python tools/mcp_health_report.py
```

Output file:
- `Evidence/MCP_HEALTH_REPORT.json`
