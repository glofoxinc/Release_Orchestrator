"""Release gate Slack DM templates from workspace.yaml / Jinja defaults."""

from __future__ import annotations

from typing import Any

import config
from release_gates import GateTicket
from template_engine import render_template


def _gates_section() -> dict[str, Any]:
    root = getattr(config, "RELEASE_GATES", {}) or {}
    return root if isinstance(root, dict) else {}


def _template_path(kind: str) -> str:
    templates = _gates_section().get("templates") or {}
    if isinstance(templates, dict):
        section = templates.get(kind) or {}
        if isinstance(section, dict):
            path = str(section.get("body") or section.get("message") or "").strip()
            if path:
                return path
    if kind == "pre_review":
        return "gates/pre_review.txt.j2"
    return "gates/post_qa.txt.j2"


def build_gate_message(
    kind: str,
    ticket: GateTicket,
    *,
    version_name: str = "",
    ready_statuses: str = "",
    passed_statuses: str = "",
) -> str:
    """Render a gate DM from template, falling back to legacy builders."""
    browse = config.JIRA_BASE_URL.rstrip("/")
    link = f"{browse}/browse/{ticket.key}"
    try:
        return render_template(
            _template_path(kind),
            assignee_name=ticket.assignee_name,
            ticket_key=ticket.key,
            status=ticket.status,
            summary=ticket.summary or "(no summary)",
            ticket_url=link,
            version_name=version_name,
            ready_statuses=ready_statuses,
            passed_statuses=passed_statuses,
        ).strip()
    except Exception:  # noqa: BLE001
        browse = config.JIRA_BASE_URL.rstrip("/")
        link = f"{browse}/browse/{ticket.key}"
        if kind == "pre_review":
            version_bit = f" for release *{version_name}*" if version_name else ""
            return (
                f"Hi {ticket.assignee_name},\n\n"
                f"*{ticket.key}* is on the upcoming release{version_bit} but is not ready for "
                f"Ticket Review (current status: *{ticket.status}*).\n"
                f"Please move it to one of: {ready_statuses}.\n\n"
                f"Summary: {ticket.summary or '(no summary)'}\n"
                f"Link: {link}"
            )
        version_bit = f" release *{version_name}*" if version_name else " this release"
        return (
            f"Hi {ticket.assignee_name},\n\n"
            f"*{ticket.key}* did not pass QA for{version_bit} (status: *{ticket.status}*) "
            f"and will be excluded from Release Notes and deployment.\n"
            f"Please update to one of: {passed_statuses}.\n\n"
            f"Summary: {ticket.summary or '(no summary)'}\n"
            f"Link: {link}"
        )


__all__ = ["build_gate_message"]
