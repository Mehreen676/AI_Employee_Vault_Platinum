# AI Employee Vault - Platinum Tier
## Judge Verification Evidence Pack

> Generated from live repo state and vault artifacts.

---

## 1) Enforced HITL Flow (Platinum)

```text
vault/Needs_Action/email/*.md
  -> vault/In_Progress/cloud/*
  -> vault/Waiting_Approval/task_<uuid>.json
  -> (human) python approve.py approve <task_file_or_id>
  -> vault/Pending_Approval/task_<uuid>.json
  -> vault/In_Progress/local/task_<uuid>.json
  -> vault/Done/task_<uuid>.json
```

Reject path:

```text
vault/Waiting_Approval/task_<uuid>.json
  -> (human) python approve.py reject <task_file_or_id> "reason"
  -> vault/Rejected/task_<uuid>.json
```

---

## 2) Judge Commands (Local or VM)

```bash
python cloud_agent.py --daemon --auto --interval 10
python approve.py list
python approve.py status
python approve.py approve task_<uuid>.json
# optional reject:
python approve.py reject task_<uuid>.json "not acceptable"
python local_executor.py --poll 2
python scripts/generate_evidence_pack.py --n 20
cat Evidence/JUDGE_PROOF.md
```

---

## 3) Oracle Proof Image Paths (Exact Relative)

- `Evidence/Oracle_Cloud_Proof/01-vm-ssh-login-proof.png`
- `Evidence/Oracle_Cloud_Proof/02-oracle-instance-details.png`
- `Evidence/Oracle_Cloud_Proof/03-repo-present-on-vm.png`
- `Evidence/Oracle_Cloud_Proof/04-cloud-agent-running.png`
- `Evidence/Oracle_Cloud_Proof/05-cloud-agent-logs.png`
- `Evidence/Oracle_Cloud_Proof/06-local-executor-running.png`
- `Evidence/Oracle_Cloud_Proof/07-local-executor-logs.png`

---

## 4) Logs To Verify

- `vault/Logs/execution_log.json` -> shows task movement to `Done`.
- `vault/Logs/health_log.json` -> process health (if watchdog used).
- `vault/Logs/approval_log.json` -> HITL approve/reject audit records.
- `history/prompt_log.json` -> append-only hash-chained prompt/event history.

---

## 5) Integrity Check

```bash
python tools/verify_history_chain.py
```

Expected:

```text
PASS: chain valid (<N> lines)
```
