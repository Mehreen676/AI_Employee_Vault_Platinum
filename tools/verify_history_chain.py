"""
Verify history/prompt_log.json hash-chain integrity.

Checks:
1) prev_hash linkage across entries
2) entry_hash recomputation against logger algorithm

Outputs:
    PASS: ...  (exit 0)
    FAIL: ...  (exit 1)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


GENESIS = "genesis"
LEGACY_GENESIS_HASH = hashlib.sha256(b"").hexdigest()


def _compute_entry_hash(record: dict) -> str:
    chain_input = "|".join(
        [
            str(record.get("log_id")),
            str(record.get("timestamp_ns")),
            str(record.get("component")),
            str(record.get("event_type")),
            str(record.get("task_id")),
            json.dumps(record.get("content", {}), sort_keys=True, ensure_ascii=False),
            str(record.get("prev_hash")),
        ]
    )
    return hashlib.sha256(chain_input.encode("utf-8")).hexdigest()


def verify(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing file: {path}"

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return False, "prompt log is empty"

    expected_prev = GENESIS

    for idx, raw in enumerate(lines, start=1):
        raw = raw.strip()
        if not raw:
            continue

        try:
            rec = json.loads(raw)
        except json.JSONDecodeError as exc:
            return False, f"line {idx}: invalid JSON ({exc})"

        prev_hash = rec.get("prev_hash")
        entry_hash = rec.get("entry_hash")
        if not isinstance(prev_hash, str) or not isinstance(entry_hash, str):
            return False, f"line {idx}: missing/invalid prev_hash or entry_hash"

        if prev_hash != expected_prev:
            return False, (
                f"line {idx}: prev_hash mismatch; "
                f"expected={expected_prev} got={prev_hash}"
            )

        computed = _compute_entry_hash(rec)
        # Backward compatibility: historical genesis may use sha256("").
        is_legacy_genesis = (
            idx == 1 and prev_hash == GENESIS and entry_hash == LEGACY_GENESIS_HASH
        )
        if entry_hash != computed and not is_legacy_genesis:
            return False, (
                f"line {idx}: entry_hash mismatch; "
                f"expected={computed} got={entry_hash}"
            )

        expected_prev = entry_hash

    return True, f"chain valid ({len(lines)} lines)"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="verify_history_chain",
        description="Verify SHA-256 hash-chain integrity of history/prompt_log.json",
    )
    parser.add_argument(
        "--path",
        default="history/prompt_log.json",
        help="Path to prompt log JSONL (default: history/prompt_log.json)",
    )
    args = parser.parse_args()

    ok, detail = verify(Path(args.path))
    if ok:
        print(f"PASS: {detail}")
        return 0
    print(f"FAIL: {detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
