# Business Goals — AI Employee Vault Platinum Tier

**Last Updated:** 2026-02-28
**Owner:** CEO / Executive Team
**Review Cycle:** Monthly

---

## Current OKRs

### Q1 2026 Objectives

| # | Objective | Key Result | Target | Status |
|---|---|---|---|---|
| 1 | Automate invoice creation | Odoo draft invoices generated via AI pipeline | 500 / month | In Progress |
| 2 | Reduce manual email triage | Gmail watcher routes 80%+ of action emails into vault | 80% routing rate | In Progress |
| 3 | Full audit compliance | 100% of AI actions logged with hash-chained entries | 100% coverage | Complete |
| 4 | Zero unreviewed payments | Payment tasks routed to human review — 0 auto-retries | 0 payment auto-retries | Complete |
| 5 | System uptime | Watchdog auto-restart — 99.5% uptime | 99.5% uptime | In Progress |

---

## Revenue Targets

| Period | Target (AED) | Source |
|---|---|---|
| Q1 2026 | AED 2,500,000 | Odoo draft invoices (confirmed by finance team) |
| Q2 2026 | AED 3,000,000 | Expanded Odoo integration + new task types |
| FY 2026 | AED 11,000,000 | Full Platinum pipeline + human approval gate |

> **Note:** All invoice amounts reported by the AI pipeline are `state='draft'`.
> Revenue is recognised only after a human confirms the invoice in Odoo.

---

## Strategic Priorities

1. **Human-in-the-loop is non-negotiable** — no AI action bypasses human review for financial tasks.
2. **Audit trail completeness** — SHA-256 hash-chained log must cover every event.
3. **Graceful degradation over failure** — Gmail outage → Deferred/; Odoo failure → Retry_Queue/.
4. **Rate limiting protects downstream systems** — email 10/hr, social 20/hr, payment 3/day.
5. **CEO briefings are generated daily** — `scripts/generate_briefing.py` runs at 07:00 UTC.

---

## Bottleneck Escalation Policy

| Trigger | Action | Owner |
|---|---|---|
| Payment task in Retry_Queue | Immediate Slack alert to finance lead | CFO |
| Cloud Agent restarts > 3×/hr | Page on-call engineer | DevOps |
| Deferred email count > 10 | Check Gmail API quota + credentials | IT |
| Daily task completion < 50% of target | Executive review | CEO |

---

*This file is read by `scripts/generate_briefing.py` to populate the Business Goals section of the daily CEO briefing.*
