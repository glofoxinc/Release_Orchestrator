"""Project-specific wrappers around :mod:`common.ai`.

Adds the terminology the release tool uses (tickets / dashboards / approvers)
on top of the generic AI helpers, and builds the exact output strings the
preview UI expects.
"""

from __future__ import annotations

import logging
from typing import Any

from common import ai as shared_ai
from consolidation import consolidate_dashboards

logger = logging.getLogger(__name__)


def summarize_ticket_set(
    extracted: list[dict[str, Any]],
    *,
    llm: shared_ai.LLM | None = None,
) -> str:
    """Return a 3-sentence executive brief for the TCKT ticket pool."""
    return shared_ai.summarize_release(extracted, llm=llm)


def rate_release_risk(
    extracted: list[dict[str, Any]],
    *,
    extra_text: str = "",
) -> shared_ai.RiskAssessment:
    """Compute a risk rating for the entire release."""
    consolidated = consolidate_dashboards(extracted)
    clients = {
        e.get("client")
        for e in extracted or []
        if e.get("client") and e.get("client") not in ("Standard", "Unknown")
    }
    text = " ".join(
        filter(
            None,
            [
                extra_text,
                *(e.get("description", "") for e in extracted or []),
                *(e.get("report", "") for e in extracted or []),
            ],
        )
    )
    return shared_ai.rate_risk(
        ticket_count=len(extracted or []),
        client_count=len(clients),
        dashboard_count=len(consolidated),
        text_blob=text,
    )


def generate_acceptance_criteria_for_ticket(
    ticket: dict[str, Any],
    *,
    llm: shared_ai.LLM | None = None,
) -> list[str]:
    """Produce acceptance-criteria bullets for a single parsed ticket."""
    description = (
        ticket.get("description")
        or ticket.get("summary")
        or ticket.get("report")
        or ""
    )
    return shared_ai.suggest_acceptance_criteria(description, llm=llm)


def enhance_draft(
    draft: dict[str, Any],
    *,
    llm: shared_ai.LLM | None = None,
) -> dict[str, Any]:
    """Annotate a ticket draft with AI-enhanced fields.

    Adds the keys ``ai_summary``, ``ai_risk``, and ``ai_acceptance_criteria``
    to a copy of ``draft`` without overwriting anything the user provided.
    """
    enhanced = dict(draft)
    extracted = draft.get("extracted") or []
    if "ai_summary" not in enhanced or not enhanced["ai_summary"]:
        enhanced["ai_summary"] = summarize_ticket_set(extracted, llm=llm)
    if "ai_risk" not in enhanced:
        enhanced["ai_risk"] = rate_release_risk(
            extracted,
            extra_text=str(draft.get("summary", "")),
        ).to_dict()
    if "ai_acceptance_criteria" not in enhanced:
        enhanced["ai_acceptance_criteria"] = [
            crit
            for t in extracted[:5]
            for crit in generate_acceptance_criteria_for_ticket(t, llm=llm)
        ]
    return enhanced


__all__ = [
    "summarize_ticket_set",
    "rate_release_risk",
    "generate_acceptance_criteria_for_ticket",
    "enhance_draft",
]
