# History Chain Verification Proof

This document defines how to verify integrity of `history/prompt_log.json`
using `tools/verify_history_chain.py`.

## Command

Run from project root:

```bash
python tools/verify_history_chain.py
```

Optional custom path:

```bash
python tools/verify_history_chain.py --path history/prompt_log.json
```

## Expected Output

- Pass case:
  - `PASS: chain valid (<N> lines)`
- Fail case:
  - `FAIL: line <X>: ...`

## What It Verifies

1. JSONL parsing line-by-line.
2. `prev_hash` linkage consistency from genesis to latest entry.
3. `entry_hash` recomputation using logger hash algorithm.
4. Backward-compatible handling for historical legacy genesis hash.

## Screenshots To Capture (for judges)

1. Terminal command execution:
   - `python tools/verify_history_chain.py`
2. PASS output visible with line count.
3. `history/prompt_log.json` first 3 lines visible.
4. `history/prompt_log.json` last 3 lines visible.
5. Script file visible:
   - `tools/verify_history_chain.py`

## Suggested Screenshot Paths

- `Evidence/Oracle_Cloud_Proof/08-history-verify-command.png`
- `Evidence/Oracle_Cloud_Proof/09-history-verify-pass.png`
- `Evidence/Oracle_Cloud_Proof/10-history-log-head.png`
- `Evidence/Oracle_Cloud_Proof/11-history-log-tail.png`
- `Evidence/Oracle_Cloud_Proof/12-history-verify-script.png`
