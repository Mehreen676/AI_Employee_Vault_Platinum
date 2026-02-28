"""Silver Cloud Agent – MCP-integrated version."""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone

# -------- OpenAI --------
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

# -------- MCP Tools --------
from mcp_server import list_tasks, move_task

# -------- Paths --------
BASE_DIR = Path(__file__).resolve().parent
NEEDS_ACTION = BASE_DIR / "Needs_Action"
DONE = BASE_DIR / "Done"
RUN_LOG = BASE_DIR / "run_log.md"
PROMPT_HISTORY = BASE_DIR / "prompt_history.md"

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_CHARS = int(os.getenv("MAX_TASK_CHARS", "6000"))


# -------- Helpers --------
def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def append_line(path: Path, text: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def build_prompt(task_text: str) -> str:
    return (
        "You are an AI employee. Summarize the task clearly in 3-6 bullet points.\n"
        "Then write a short 'Next actions' section (1-3 bullets).\n"
        "Keep it concise. Do NOT invent details.\n\n"
        f"TASK:\n{task_text[:MAX_CHARS]}"
    )


def openai_summarize(prompt: str) -> tuple[str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key or OpenAI is None:
        return (
            "Silver Agent processed this task. (fallback: OpenAI not configured)",
            "fallback",
        )

    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        text = resp.choices[0].message.content.strip()
        if not text:
            return ("Summary generated but empty response.", "openai_empty")
        return (text, "openai_ok")
    except Exception as e:
        return (f"(OpenAI error fallback) {e}", "openai_error")


# -------- Main --------
def main() -> None:
    print("=== Silver MCP Agent Running ===")

    NEEDS_ACTION.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)

    if not RUN_LOG.exists():
        RUN_LOG.write_text("# Run Log\n\n", encoding="utf-8")
    if not PROMPT_HISTORY.exists():
        PROMPT_HISTORY.write_text("# Prompt History\n\n", encoding="utf-8")

    # 🔥 MCP TOOL USED HERE
    file_names = list_tasks(NEEDS_ACTION)

    if not file_names:
        print("No tasks found in Needs_Action/.")
        append_line(RUN_LOG, f"{utc_ts()} - No tasks found.\n")
        print("=== Done ===")
        return

    for name in file_names:
        file_path = NEEDS_ACTION / name
        original = file_path.read_text(encoding="utf-8", errors="ignore").strip()

        prompt = build_prompt(original)
        summary, status = openai_summarize(prompt)

        output = (
            "# Processed Task\n\n"
            "## Original Content\n"
            f"{original}\n\n"
            "## AI Summary\n"
            f"{summary}\n\n"
            "Status: Completed\n"
        )

        # Write processed output
        dest = DONE / name
        dest.write_text(output, encoding="utf-8")

        # 🔥 MCP TOOL USED HERE
        move_task(file_path, dest)

        append_line(RUN_LOG, f"{utc_ts()} - Processed: {name} | {status}\n")

        prompt_log = "fallback" if status == "fallback" else prompt
        append_line(
            PROMPT_HISTORY,
            f"---\n[{utc_ts()}] FILE: {name}\nMODEL: {MODEL}\nSTATUS: {status}\nPROMPT:\n{prompt_log}\n---\n\n",
        )

        print(f"Processed: {name} ({status})")

    print("=== Done ===")


if __name__ == "__main__":
    main()
