"""
Cross-Domain Router – Personal + Business task classification.

Reads task content and routes to the appropriate domain folder
(Personal/ or Business/) while maintaining unified processing pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path
from audit_logger import log_action

SERVER_NAME = "domain_router"

# Keywords for domain classification
BUSINESS_KEYWORDS = [
    "invoice", "meeting", "quarterly", "revenue", "client", "project",
    "deadline", "stakeholder", "budget", "sprint", "deployment", "release",
    "contract", "proposal", "vendor", "compliance", "audit", "report",
    "roadmap", "milestone", "kpi", "okr", "pipeline", "onboarding",
    "payroll", "hr", "marketing", "sales", "operations", "strategy",
]

PERSONAL_KEYWORDS = [
    "grocery", "doctor", "appointment", "birthday", "vacation", "gym",
    "recipe", "family", "hobby", "travel", "personal", "reminder",
    "shopping", "health", "fitness", "pet", "home", "garden",
]


def classify_task(content: str) -> str:
    """Classify task content as 'business' or 'personal'.

    Uses keyword matching + domain header detection.
    Returns 'business' or 'personal'.
    """
    text = content.lower()

    # Check for explicit domain header
    domain_match = re.search(r"domain:\s*(business|personal)", text)
    if domain_match:
        domain = domain_match.group(1)
        log_action(SERVER_NAME, "classify_task", {"method": "header", "domain": domain})
        return domain

    # Keyword scoring
    biz_score = sum(1 for kw in BUSINESS_KEYWORDS if kw in text)
    per_score = sum(1 for kw in PERSONAL_KEYWORDS if kw in text)

    if biz_score > per_score:
        domain = "business"
    elif per_score > biz_score:
        domain = "personal"
    else:
        # Default to business for ambiguous tasks
        domain = "business"

    log_action(SERVER_NAME, "classify_task", {
        "method": "keyword_score",
        "domain": domain,
        "biz_score": biz_score,
        "per_score": per_score,
    })
    return domain


def route_task(task_name: str, content: str, base_dir: str | Path) -> Path:
    """Classify and return the appropriate domain subfolder path."""
    base_dir = Path(base_dir)
    domain = classify_task(content)

    if domain == "business":
        target = base_dir / "Business"
    else:
        target = base_dir / "Personal"

    target.mkdir(parents=True, exist_ok=True)
    log_action(SERVER_NAME, "route_task", {"task": task_name, "domain": domain, "target": str(target)})
    return target


def get_all_domain_tasks(base_dir: str | Path) -> dict[str, list[str]]:
    """Return all tasks grouped by domain."""
    base_dir = Path(base_dir)
    result = {"business": [], "personal": []}

    biz_dir = base_dir / "Business"
    per_dir = base_dir / "Personal"

    if biz_dir.is_dir():
        result["business"] = sorted(f.name for f in biz_dir.glob("*.md") if f.name != ".gitkeep")
    if per_dir.is_dir():
        result["personal"] = sorted(f.name for f in per_dir.glob("*.md") if f.name != ".gitkeep")

    log_action(SERVER_NAME, "get_all_domain_tasks", {
        "business_count": len(result["business"]),
        "personal_count": len(result["personal"]),
    })
    return result


if __name__ == "__main__":
    print(f"=== {SERVER_NAME} Ready ===")
    print("Tools: classify_task, route_task, get_all_domain_tasks")
