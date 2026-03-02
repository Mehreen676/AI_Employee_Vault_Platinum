# Evidence Directory

This directory contains judge-facing proof artifacts for the AI Employee Vault – Platinum Tier.

---

## Files

### `JUDGE_PROOF.md`

A structured evidence pack generated from **live filesystem state** at the time of the last run.

**Contents:**
- UTC generation timestamp
- Vault state counts (`vault/Pending_Approval/`, `vault/Done/`)
- Last 5 execution log entries from `vault/Logs/execution_log.json` — showing task IDs, types, actions, and timestamps
- Last 5 prompt history entries from `history/prompt_log.json` — showing component, event type, and summary
- Integrity statement referencing the SHA-256 hash chain

**This file is committed to the repository as a static proof snapshot.** It was generated from real execution state on the Oracle Cloud VM (`me-dubai-1`, Ubuntu 20.04).

### `RUN_CHECKLIST.md`

A quick-start command reference for running the full Platinum pipeline end-to-end.

---

## How Judges Can Regenerate JUDGE_PROOF.md

Run from the project root on any machine with vault data present:

```bash
python3 scripts/generate_evidence_pack.py --n 20
cat Evidence/JUDGE_PROOF.md
```

Or request N entries from the prompt log:

```bash
python3 scripts/generate_evidence_pack.py --n 50
```

The script reads:
- `vault/Pending_Approval/*.json` — pending task count
- `vault/Done/*.json` — completed task count
- `vault/Logs/execution_log.json` — JSONL execution history
- `history/prompt_log.json` — SHA-256 hash-chained prompt + event log

---

## Integrity Guarantee

Every entry in `history/prompt_log.json` is SHA-256 hash-chained:

```
[Genesis] → [Entry 1] → [Entry 2] → ... → [Entry N]
```

Each entry's `entry_hash` covers its content plus the previous entry's hash.
Any modification or deletion of any entry breaks the chain — providing mathematical proof of tampering.

The log is append-only (`os.fsync()` on every write) and is written exclusively by `logging/prompt_logger.py`.

---

*AI Employee Vault – Platinum Tier | Evidence Pack | Oracle Cloud VM: me-dubai-1*
