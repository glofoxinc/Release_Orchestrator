"""AI Ticket Creator — parse natural-language descriptions into structured Jira tickets.

Extracts summary, description, issue type, priority, and component from free-form text,
then uses `jira_client.create_issue` to create the ticket in Jira.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import config
import jira_client
from ai_triage import triage_ticket

logger = logging.getLogger(__name__)

# ── Issue type detection ─────────────────────────────────────────────────────

_BUG_PATTERNS = re.compile(
    r"\b(bug|defect|error|broken|crash|fix|issue|fail|not working|regression|500|404|exception)\b",
    re.IGNORECASE,
)

_STORY_PATTERNS = re.compile(
    r"\b(as a user|user story|feature|new functionality|i want|so that|enable|allow users)\b",
    re.IGNORECASE,
)


def _detect_issue_type(text: str) -> str:
    """Detect issue type from text signals. Returns 'Bug', 'Story', or 'Task'."""
    bug_score = len(_BUG_PATTERNS.findall(text))
    story_score = len(_STORY_PATTERNS.findall(text))

    if bug_score > story_score and bug_score >= 2:
        return "Bug"
    if story_score > bug_score and story_score >= 1:
        return "Story"
    return "Task"


# ── Summary extraction ───────────────────────────────────────────────────────

def _extract_summary(text: str) -> str:
    """Extract a concise summary (first meaningful sentence or line, capped at 120 chars)."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return "New ticket"

    first_line = lines[0]
    first_line = re.sub(r"^(please|can you|could you|i need|we need)\s+", "", first_line, flags=re.IGNORECASE)
    first_line = first_line.strip().rstrip(".")

    if len(first_line) <= 120:
        return first_line

    truncated = first_line[:117]
    last_space = truncated.rfind(" ")
    if last_space > 80:
        truncated = truncated[:last_space]
    return truncated + "..."


def _extract_description(text: str, summary: str) -> str:
    """Build the description body, removing the summary line if it was the first line."""
    lines = text.strip().splitlines()
    if not lines:
        return ""

    if lines[0].strip().startswith(summary[:40]):
        remaining = "\n".join(lines[1:]).strip()
    else:
        remaining = text.strip()

    return remaining or summary


# ── Priority extraction ──────────────────────────────────────────────────────

_PRIORITY_MAP: dict[str, str] = {
    "critical": "Highest",
    "highest": "Highest",
    "high": "High",
    "urgent": "High",
    "medium": "Medium",
    "normal": "Medium",
    "low": "Low",
    "lowest": "Lowest",
    "minor": "Low",
    "trivial": "Lowest",
}


def _extract_priority(text: str) -> str:
    """Extract priority from text, defaulting to Medium."""
    text_lower = text.lower()

    priority_match = re.search(r"priority[:\s]*(critical|highest|high|urgent|medium|normal|low|lowest|minor|trivial)",
                               text_lower)
    if priority_match:
        return _PRIORITY_MAP.get(priority_match.group(1), "Medium")

    if any(kw in text_lower for kw in ("critical", "outage", "production down", "emergency")):
        return "Highest"
    if any(kw in text_lower for kw in ("urgent", "blocker", "production")):
        return "High"
    if any(kw in text_lower for kw in ("nice to have", "cosmetic", "minor")):
        return "Low"

    return "Medium"


# ── Main creation function ───────────────────────────────────────────────────

def parse_ticket_from_nl(description: str, project_key: str) -> dict[str, Any]:
    """Parse a natural-language description into structured ticket fields.

    Returns a dict with: summary, description, issue_type, priority, component
    (suitable for preview before creation).
    """
    if not description or not description.strip():
        return {
            "summary": "New ticket",
            "description": "",
            "issue_type": "Task",
            "priority": "Medium",
            "component": "General",
            "triage": None,
        }

    summary = _extract_summary(description)
    body = _extract_description(description, summary)
    issue_type = _detect_issue_type(description)
    priority = _extract_priority(description)

    triage = triage_ticket(description, project_key)
    component = triage.get("component", "General")

    if triage.get("priority") == "High" and priority == "Medium":
        priority = "High"

    return {
        "summary": summary,
        "description": body,
        "issue_type": issue_type,
        "priority": priority,
        "component": component,
        "triage": triage,
    }


def build_jira_create_fields(parsed: dict[str, Any], project_key: str) -> dict[str, Any]:
    """Map parsed NL fields to Jira REST ``fields`` payload."""
    create_fields: dict[str, Any] = {
        "priority": {"name": parsed["priority"]},
    }

    if parsed.get("description"):
        create_fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": parsed["description"]}],
                }
            ],
        }

    component = jira_client.resolve_component(project_key, parsed.get("component", ""))
    if component:
        create_fields["components"] = [component]

    labels: list[str] = []
    issue_type = (parsed.get("issue_type") or "").strip()
    if issue_type:
        labels.append(f"ai-{issue_type.lower()}")

    comp_label = (parsed.get("component") or "").strip()
    if comp_label and comp_label.lower() != "general":
        labels.append(comp_label.replace(" ", "-"))

    triage = parsed.get("triage") or {}
    assignee_hint = (triage.get("suggested_assignee") or "").strip()
    if assignee_hint and assignee_hint.lower() != "unassigned":
        labels.append(f"triage-{assignee_hint}")

    if labels:
        create_fields["labels"] = sorted(set(labels))

    return create_fields


def create_ticket_from_nl(
    description: str,
    project_key: str,
    *,
    issue_type_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Parse NL input and create a Jira ticket.

    Parameters
    ----------
    description : str
        Free-form natural language describing the work or bug.
    project_key : str
        Target Jira project (e.g. "PIC", "AN", "TCKT").
    issue_type_id : str | None
        Optional Jira issue type ID override. When omitted, resolved from Jira createmeta.
    dry_run : bool
        If True, return parsed fields without creating in Jira.

    Returns
    -------
    dict with keys: key, url, fields (parsed), triage
    """
    parsed = parse_ticket_from_nl(description, project_key)

    if dry_run:
        return {
            "key": None,
            "url": None,
            "fields": parsed,
            "dry_run": True,
        }

    if issue_type_id:
        resolved_type_id = issue_type_id
    else:
        resolved_type_id = jira_client.resolve_issue_type_id(
            project_key,
            parsed["issue_type"],
        )

    create_fields = build_jira_create_fields(parsed, project_key)

    result = jira_client.create_issue(
        project_key=project_key,
        issue_type_id=resolved_type_id,
        summary=parsed["summary"],
        fields=create_fields,
    )

    ticket_key = result.get("key", "")
    base_url = config.JIRA_BASE_URL.rstrip("/")
    url = f"{base_url}/browse/{ticket_key}" if ticket_key else ""

    return {
        "key": ticket_key,
        "url": url,
        "fields": parsed,
        "jira_fields": create_fields,
        "triage": parsed.get("triage"),
    }


__all__ = ["parse_ticket_from_nl", "create_ticket_from_nl", "build_jira_create_fields"]
