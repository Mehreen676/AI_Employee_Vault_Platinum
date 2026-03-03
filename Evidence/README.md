# Evidence Directory

This directory contains judge-facing proof artifacts for the AI Employee Vault - Platinum Tier.

---

## Files

### `JUDGE_PROOF.md`

A structured evidence pack generated from live filesystem state at the time of the last run.

Contents include:
- UTC generation timestamp
- Vault state counts (`vault/Waiting_Approval/`, `vault/Pending_Approval/`, `vault/Done/`)
- Last 5 execution log entries from `vault/Logs/execution_log.json`
- Last 5 prompt history entries from `history/prompt_log.json`
- Integrity statement referencing SHA-256 hash chain

### `RUN_CHECKLIST.md`

Exact local/cloud run commands plus verification steps.

### `HISTORY_PROOF.md`

How to verify `history/prompt_log.json` chain integrity with:
- `tools/verify_history_chain.py`

### `MCP_PROOF.md`

Router + registry proof notes plus MCP health report generation command.

### `Oracle_Cloud_Proof/` (image evidence)

Exact proof image paths:
- `Evidence/Oracle_Cloud_Proof/01-vm-ssh-login-proof.png`
- `Evidence/Oracle_Cloud_Proof/02-oracle-instance-details.png`
- `Evidence/Oracle_Cloud_Proof/03-repo-present-on-vm.png`
- `Evidence/Oracle_Cloud_Proof/04-cloud-agent-running.png`
- `Evidence/Oracle_Cloud_Proof/05-cloud-agent-logs.png`
- `Evidence/Oracle_Cloud_Proof/06-local-executor-running.png`
- `Evidence/Oracle_Cloud_Proof/07-local-executor-logs.png`

---

## Regenerate JUDGE_PROOF.md

From project root:

```bash
python scripts/generate_evidence_pack.py --n 20
cat Evidence/JUDGE_PROOF.md
```

The generator reads:
- `vault/Waiting_Approval/*.json`
- `vault/Pending_Approval/*.json`
- `vault/Done/*.json`
- `vault/Logs/execution_log.json`
- `history/prompt_log.json`

---

## Integrity Guarantee

Every entry in `history/prompt_log.json` is SHA-256 hash-chained:

`[Genesis] -> [Entry 1] -> [Entry 2] -> ... -> [Entry N]`

Any modification or deletion breaks chain verification.

