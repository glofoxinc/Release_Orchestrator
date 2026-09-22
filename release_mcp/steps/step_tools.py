"""MCP-facing helpers for per-step status and onboarding readiness."""

from __future__ import annotations

from typing import Any

import team_crew

from release_mcp import onboarding, step_ux
from release_mcp.steps.catalog import RELEASE_STEPS, step_catalog_payload


def release_step_status(step_id: str = "") -> dict[str, Any]:
    """Status for one release step or the full 8-step catalog.

    Safe without Jira credentials for onboarding/setup steps.
    """
    sid = (step_id or "").strip().lower()
    catalog = step_catalog_payload()
    if not sid:
        assessment = onboarding.assess_setup(from_mcp=True)
        return {
            "catalog": catalog,
            "onboarding": {
                "fully_ready": assessment.get("fully_ready"),
                "next_setup_step": (assessment.get("next_setup_step") or {}).get("id"),
            },
            "team_crew": team_crew.team_crew_status(),
            "hint": "Say **welcome onboard** once · then **full release** each week.",
        }

    match = next((s for s in RELEASE_STEPS if s["id"] == sid), None)
    if not match:
        return {
            "ok": False,
            "error": f"Unknown step {step_id!r}. Use empty step_id for full catalog.",
            "known_steps": [s["id"] for s in RELEASE_STEPS],
        }

    ux = step_ux.STEP_UX.get(sid, {})
    extra: dict[str, Any] = {}
    if sid == "onboarding":
        assessment = onboarding.assess_setup(from_mcp=True)
        extra["fully_ready"] = assessment.get("fully_ready")
        extra["team_crew"] = team_crew.team_crew_status()
    elif sid == "ticket_review":
        extra["team_scope_hint"] = "Call team_scope_status(PIC) and team_scope_status(AN) before fetch."
    elif sid == "slack":
        extra["reference"] = "Call slack_reference() for SHIPIT-17191 gold-standard copy."

    return {
        "ok": True,
        "step": match,
        "progress": step_ux.progress_header(sid),
        "hint": ux.get("hint") or "",
        "say_first": step_ux.primary_phrases(sid, limit=3),
        **extra,
    }
