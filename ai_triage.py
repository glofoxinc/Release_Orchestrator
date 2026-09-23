"""AI-powered ticket triage — classify incoming tickets by component, priority, and assignee.

Primary engine is rule-based (regex + keyword matching) for deterministic, fast results.
When OPENAI_API_KEY or AZURE_OPENAI_API_KEY is set, an optional LLM pass refines the
classification and provides natural-language reasoning.
"""

from __future__ import annotations

import logging
from typing import Any

from common.ai import LLM, _provider_available, _resolve_llm

logger = logging.getLogger(__name__)

# ── Component keyword mappings ───────────────────────────────────────────────

_COMPONENT_KEYWORDS: dict[str, list[str]] = {
    "Data Pipeline": [
        "pipeline", "etl", "ingestion", "data flow", "databricks", "spark",
        "lakehouse", "delta", "notebook", "adf", "data factory",
    ],
    "Dashboard": [
        "dashboard", "report", "power bi", "powerbi", "pbi", "visual",
        "semantic model", "dataset", "measure", "dax", "embed",
    ],
    "Infrastructure": [
        "infra", "server", "deploy", "ci/cd", "cicd", "docker", "kubernetes",
        "k8s", "terraform", "azure", "aws", "cloud", "vm", "network",
    ],
    "API": [
        "api", "endpoint", "rest", "graphql", "microservice", "service",
        "integration", "webhook",
    ],
    "Security": [
        "security", "auth", "authentication", "authorization", "permission",
        "role", "rbac", "sso", "token", "vulnerability", "cve",
    ],
    "Frontend": [
        "ui", "frontend", "react", "angular", "css", "layout", "button",
        "form", "page", "component", "streamlit",
    ],
    "Database": [
        "database", "db", "sql", "query", "table", "schema", "migration",
        "index", "stored procedure", "snowflake",
    ],
}

# ── Priority heuristics ──────────────────────────────────────────────────────

_HIGH_PRIORITY_KEYWORDS = [
    "production", "prod", "urgent", "blocker", "critical", "outage",
    "down", "broken", "emergency", "hotfix", "security vulnerability",
    "data loss", "revenue impact",
]

_LOW_PRIORITY_KEYWORDS = [
    "nice to have", "enhancement", "cosmetic", "minor", "typo",
    "documentation", "docs", "refactor", "cleanup", "tech debt",
]

# ── Assignee suggestion heuristics ───────────────────────────────────────────

_COMPONENT_ASSIGNEE_MAP: dict[str, str] = {
    "Data Pipeline": "data-engineering-team",
    "Dashboard": "bi-team",
    "Infrastructure": "devops-team",
    "API": "backend-team",
    "Security": "security-team",
    "Frontend": "frontend-team",
    "Database": "dba-team",
}


def _classify_component(text: str) -> tuple[str, float]:
    """Match text against component keywords; return (component, confidence)."""
    text_lower = text.lower()
    scores: dict[str, int] = {}

    for component, keywords in _COMPONENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[component] = score

    if not scores:
        return "General", 0.3

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    max_possible = len(_COMPONENT_KEYWORDS[best])
    confidence = min(0.95, 0.5 + (scores[best] / max_possible) * 0.45)
    return best, confidence


def _classify_priority(text: str) -> tuple[str, float]:
    """Determine priority from keyword signals."""
    text_lower = text.lower()

    high_hits = sum(1 for kw in _HIGH_PRIORITY_KEYWORDS if kw in text_lower)
    low_hits = sum(1 for kw in _LOW_PRIORITY_KEYWORDS if kw in text_lower)

    if high_hits >= 2:
        return "High", 0.9
    if high_hits == 1:
        return "High", 0.7
    if low_hits >= 2:
        return "Low", 0.85
    if low_hits == 1:
        return "Low", 0.6
    return "Medium", 0.5


def _suggest_assignee(component: str) -> str:
    """Suggest a team/assignee based on classified component."""
    return _COMPONENT_ASSIGNEE_MAP.get(component, "unassigned")


def _rule_based_triage(ticket_text: str) -> dict[str, Any]:
    """Pure rule-based classification."""
    component, comp_conf = _classify_component(ticket_text)
    priority, pri_conf = _classify_priority(ticket_text)
    assignee = _suggest_assignee(component)

    avg_confidence = round((comp_conf + pri_conf) / 2, 3)

    reasoning_parts = []
    if component != "General":
        reasoning_parts.append(f"Matched component '{component}' via keyword signals")
    else:
        reasoning_parts.append("No strong component signal; defaulting to General")
    reasoning_parts.append(f"Priority '{priority}' based on urgency keywords")
    reasoning_parts.append(f"Suggested assignee: {assignee}")

    return {
        "component": component,
        "priority": priority,
        "suggested_assignee": assignee,
        "reasoning": ". ".join(reasoning_parts) + ".",
        "confidence": avg_confidence,
    }


def _llm_enhanced_triage(ticket_text: str, project_key: str, base_result: dict, llm: LLM) -> dict[str, Any]:
    """Refine rule-based result with LLM reasoning."""
    prompt = (
        f"You are a Jira ticket triage assistant for project {project_key}.\n"
        f"Classify this ticket and validate or improve the initial classification.\n\n"
        f"Ticket text:\n{ticket_text[:2000]}\n\n"
        f"Initial classification:\n"
        f"- Component: {base_result['component']}\n"
        f"- Priority: {base_result['priority']}\n"
        f"- Suggested assignee: {base_result['suggested_assignee']}\n\n"
        f"Respond in exactly this format (no extra text):\n"
        f"Component: <component name>\n"
        f"Priority: <High|Medium|Low>\n"
        f"Assignee: <team or person>\n"
        f"Reasoning: <one sentence explaining your classification>\n"
        f"Confidence: <0.0 to 1.0>"
    )

    try:
        response = llm(prompt).strip()
        result = dict(base_result)

        for line in response.splitlines():
            line = line.strip()
            if line.lower().startswith("component:"):
                result["component"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("priority:"):
                val = line.split(":", 1)[1].strip()
                if val in ("High", "Medium", "Low"):
                    result["priority"] = val
            elif line.lower().startswith("assignee:"):
                result["suggested_assignee"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("reasoning:"):
                result["reasoning"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("confidence:"):
                try:
                    result["confidence"] = round(float(line.split(":", 1)[1].strip()), 3)
                except ValueError:
                    pass

        return result
    except Exception:
        logger.debug("LLM triage enhancement failed; using rule-based result", exc_info=True)
        return base_result


def triage_ticket(
    ticket_text: str,
    project_key: str,
    *,
    llm: LLM | None = None,
) -> dict[str, Any]:
    """Classify an incoming ticket by component, priority, and suggested assignee.

    Parameters
    ----------
    ticket_text : str
        The ticket summary + description text to classify.
    project_key : str
        The Jira project key (e.g. "PIC", "AN") for context.
    llm : callable, optional
        Injectable LLM function for testing. If None, uses configured provider.

    Returns
    -------
    dict with keys: component, priority, suggested_assignee, reasoning, confidence
    """
    if not ticket_text or not ticket_text.strip():
        return {
            "component": "General",
            "priority": "Medium",
            "suggested_assignee": "unassigned",
            "reasoning": "Empty ticket text provided.",
            "confidence": 0.0,
        }

    base_result = _rule_based_triage(ticket_text)

    if llm is not None:
        return _llm_enhanced_triage(ticket_text, project_key, base_result, llm)

    if _provider_available():
        try:
            resolved_llm = _resolve_llm()
            return _llm_enhanced_triage(ticket_text, project_key, base_result, resolved_llm)
        except Exception:
            logger.debug("LLM provider unavailable; using rule-based triage", exc_info=True)

    return base_result


__all__ = ["triage_ticket"]
