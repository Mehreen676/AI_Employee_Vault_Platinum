# Claude Run Prompt — Process Task

## Context
You must act as the AI Employee Agent. Follow:
- ./CLAUDE.md
- ./skills/process_task.SKILL.md

## Task File
- ./Needs_Action/weekly_sales.md

## Instructions
1) Read ./skills/process_task.SKILL.md
2) Read ./Needs_Action/weekly_sales.md
3) Rewrite ./Needs_Action/weekly_sales.md using the skill template
4) Move ./Needs_Action/weekly_sales.md to ./Done/weekly_sales.md
5) Append a log line to ./run_log.md:
   [YYYY-MM-DD HH:MM] weekly_sales.md -> TASK_COMPLETE
6) Reply only: TASK_COMPLETE
