"""
tools/generate_architecture_diagram.py
---------------------------------------
Architecture Diagram Generator — Gold Tier

Generates two files:
  Evidence/ARCH_DIAGRAM.txt  — ASCII art diagram
  Evidence/ARCH_DIAGRAM.md   — Mermaid flowchart diagram

Flow: Inbox → Agent → MCP → HITL → Done → CEO Briefing
"""

from __future__ import annotations

import io
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 output on Windows terminals that default to cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
elif sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / "Evidence"


# ── ASCII diagram ─────────────────────────────────────────────────────────────

ASCII_DIAGRAM = r"""
╔══════════════════════════════════════════════════════════════╗
║          AI Employee Vault — Gold Tier Architecture          ║
╚══════════════════════════════════════════════════════════════╝

  ┌─────────────────────────────────────────────────────────┐
  │           INPUT LAYER                                   │
  │                                                         │
  │   Gmail (OAuth)          Manual Drop                    │
  │        │                      │                         │
  │        └──────────┬───────────┘                         │
  │                   │                                     │
  │            [Inbox/ folder]                              │
  │                   │                                     │
  │          inbox_watcher.py                               │
  │       (adds YAML frontmatter)                           │
  └───────────────────┼─────────────────────────────────────┘
                      │
                      ▼
  ┌─────────────────────────────────────────────────────────┐
  │           GOLD AGENT  (gold_agent.py)                   │
  │           Ralph Wiggum Autonomous Loop                  │
  │                                                         │
  │   [Needs_Action/]  ◄──── stage_inbox()                  │
  │         │                                               │
  │         ▼                                               │
  │   ┌─────────────────────────────────────────────┐       │
  │   │            MCP LAYER                        │       │
  │   │                                             │       │
  │   │  mcp_file_ops     — CRUD vault files        │       │
  │   │  mcp_email_ops    — classify / parse email  │       │
  │   │  mcp_calendar_ops — schedule / priority     │       │
  │   │  mcp_audit_ops    — compliance queries      │       │
  │   │                                             │       │
  │   │  + stubs: gmail · odoo · browser · social   │       │
  │   └──────────────────┬──────────────────────────┘       │
  │                      │                                  │
  │                      ▼                                  │
  │   ┌─────────────────────────────────────────────┐       │
  │   │            HITL GATE  (hitl.py)             │       │
  │   │                                             │       │
  │   │  sensitive keyword? ──YES──►[Pending_Approval/]──►  │
  │   │        │                      human review          │
  │   │        NO                     approve / reject      │
  │   │        │                            │               │
  │   │        │◄───────────── approved ────┘               │
  │   └────────┼────────────────────────────────────────────┘
  │            │
  │            ▼
  │   classify → OpenAI summarize → domain_router.py
  │         │               │
  │   [Personal/]     [Business/]
  │         │               │
  │         └───────┬───────┘
  │                 ▼
  │            [Done/ folder]
  └─────────────────┼───────────────────────────────────────┘
                    │
                    ▼
  ┌─────────────────────────────────────────────────────────┐
  │           OUTPUT LAYER                                  │
  │                                                         │
  │   ceo_briefing.py  ──►  [Briefings/CEO_Briefing_*.md]  │
  │   audit_logger.py  ──►  [Logs/*.json]                  │
  │   vault_logger.py  ──►  [Logs/Runs/run_*.md]           │
  │   Neon DB          ──►  agent_runs + events tables      │
  │   Evidence/        ──►  MCP_HEALTH_REPORT.json +        │
  │                         REGISTERED_MCP_TOOLS.json +     │
  │                         ARCH_DIAGRAM.*                  │
  └─────────────────────────────────────────────────────────┘

Legend:
  [Folder/]   = filesystem folder (vault)
  module.py   = Python module
  MCP LAYER   = Model Context Protocol servers (tools)
  HITL GATE   = Human-in-the-Loop approval gate

Generated: {generated}
"""


# ── Mermaid diagram ───────────────────────────────────────────────────────────

MERMAID_TEMPLATE = """\
# AI Employee Vault — Architecture Diagram

> Generated: {generated}

## System Flow

```mermaid
flowchart TD
    %% Input sources
    Gmail([📧 Gmail OAuth])
    Manual([📄 Manual Drop])
    Inbox[/"📥 Inbox/"/]

    %% Watcher
    IW["inbox_watcher.py\\n(YAML frontmatter)"]

    %% Agent core
    NA[/"⚙️ Needs_Action/"/]
    Agent["🤖 gold_agent.py\\nRalph Wiggum Loop"]

    %% MCP Layer
    subgraph MCP["MCP Layer"]
        FileOps["mcp_file_ops\\n(CRUD vault files)"]
        EmailOps["mcp_email_ops\\n(classify / parse)"]
        CalOps["mcp_calendar_ops\\n(schedule / priority)"]
        AuditOps["mcp_audit_ops\\n(compliance queries)"]
        Stubs["stubs: gmail · odoo\\nbrowser · social"]
    end

    %% HITL
    HITL{"🛑 HITL Gate\\nhitl.py"}
    Pending[/"⏳ Pending_Approval/"/]
    Human(["👤 Human Review\\napprove.py"])
    Approved[/"✅ Approved/"/]

    %% Processing
    OpenAI["OpenAI\\nSummarize"]
    DomainRouter["domain_router.py"]

    %% Output folders
    Personal[/"🏠 Personal/"/]
    Business[/"💼 Business/"/]
    Done[/"✅ Done/"/]

    %% Output layer
    CEO["ceo_briefing.py"]
    Briefings[/"📊 Briefings/"/]
    Logs[/"🗂️ Logs/\\nJSON audit trail"/]
    NeonDB[("🐘 Neon Postgres\\nagent_runs · events")]
    Evidence[/"📋 Evidence/"/]

    %% ── Edges ──────────────────────────────────────
    Gmail --> Inbox
    Manual --> Inbox
    Inbox --> IW --> NA --> Agent

    Agent --> MCP
    MCP --> HITL

    HITL -- sensitive --> Pending --> Human
    Human -- approve --> Approved --> Agent
    Human -- reject --> Done

    HITL -- safe --> OpenAI --> DomainRouter
    DomainRouter --> Personal & Business --> Done

    Done --> CEO --> Briefings
    Agent --> Logs --> NeonDB
    Agent --> Evidence

    %% ── Styles ──────────────────────────────────────
    classDef folder    fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    classDef agent     fill:#fef9c3,stroke:#ca8a04,color:#713f12
    classDef mcp       fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef hitl      fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    classDef output    fill:#f3e8ff,stroke:#9333ea,color:#3b0764
    classDef external  fill:#f1f5f9,stroke:#64748b,color:#1e293b

    class Inbox,NA,Pending,Approved,Personal,Business,Done,Briefings,Logs,Evidence folder
    class Agent,IW,DomainRouter,OpenAI,CEO agent
    class FileOps,EmailOps,CalOps,AuditOps,Stubs mcp
    class HITL hitl
    class NeonDB output
    class Gmail,Manual,Human external
```

## Component Summary

| Component | File | Role |
|-----------|------|------|
| Gold Agent | `gold_agent.py` | Autonomous Ralph Wiggum loop |
| Inbox Watcher | `inbox_watcher.py` | Normalises Inbox/ → Needs_Action/ |
| MCP File Ops | `mcp_file_ops.py` | Vault CRUD (list/read/write/move/delete) |
| MCP Email Ops | `mcp_email_ops.py` | Classify sender, parse headers, draft reply |
| MCP Calendar Ops | `mcp_calendar_ops.py` | Schedule, prioritise, briefing-due check |
| MCP Audit Ops | `mcp_audit_ops.py` | Compliance queries, error log, summary |
| HITL Gate | `hitl.py` | Sensitive-keyword detection + approval flow |
| Domain Router | `domain_router.py` | Personal / Business classifier |
| CEO Briefing | `ceo_briefing.py` | Weekly executive markdown report |
| Audit Logger | `audit_logger.py` | Per-action JSON → Logs/ + Neon DB |
"""


# ── main ──────────────────────────────────────────────────────────────────────

def run() -> tuple[Path, Path]:
    EVIDENCE_DIR.mkdir(exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ASCII diagram — only one {generated} placeholder, safe to use replace()
    txt_path = EVIDENCE_DIR / "ARCH_DIAGRAM.txt"
    txt_path.write_text(ASCII_DIAGRAM.replace("{generated}", ts), encoding="utf-8")

    # Mermaid diagram — use replace() to avoid .format() choking on Mermaid {curly} syntax
    md_path = EVIDENCE_DIR / "ARCH_DIAGRAM.md"
    md_path.write_text(MERMAID_TEMPLATE.replace("{generated}", ts), encoding="utf-8")

    return txt_path, md_path


def _print_summary(txt_path: Path, md_path: Path) -> None:
    w = 62
    print("=" * w)
    print("  Architecture Diagram Generator — Gold Tier")
    print("=" * w)
    print(f"  ASCII   → {txt_path.relative_to(BASE_DIR)}")
    print(f"  Mermaid → {md_path.relative_to(BASE_DIR)}")
    print()
    print("  ASCII preview (first 20 lines):")
    print("  " + "-" * 58)
    lines = txt_path.read_text(encoding="utf-8").splitlines()
    for line in lines[1:21]:
        print(f"  {line}")
    print("  " + "-" * 58)
    print("=" * w)


if __name__ == "__main__":
    txt_path, md_path = run()
    _print_summary(txt_path, md_path)
    sys.exit(0)
