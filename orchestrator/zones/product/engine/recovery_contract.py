"""Unified recovery/persistence contract for Platform and MCP wizard sessions.

Defines which release-critical domains must survive restarts and how to
compare Platform draft state with MCP wizard session artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import deploy_draft
import release_session
from persistence.schema import PLATFORM_RECOVERY_KEYS as _SCHEMA_KEYS
from session_persist import RELEASE_NOTES_PERSIST_KEYS, SERVICE_TICKET_PERSIST_KEYS

# Release-critical domains both surfaces must preserve.
RECOVERY_DOMAINS: tuple[str, ...] = (
    "snapshot",
    "release_notes",
    "sharepoint",
    "service_ticket",
    "slack",
    "teams",
    "deploy",
)

PLATFORM_RECOVERY_KEYS: tuple[str, ...] = _SCHEMA_KEYS


@dataclass
class RecoverySnapshot:
    """Normalized recovery view for parity checks."""

    domains: dict[str, bool] = field(default_factory=dict)
    missing_keys: list[str] = field(default_factory=list)

    @property
    def restorable(self) -> bool:
        return any(self.domains.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "restorable": self.restorable,
            "domains": dict(self.domains),
            "missing_keys": list(self.missing_keys),
        }


def _domain_flags_from_mapping(data: dict[str, Any]) -> dict[str, bool]:
    session = data.get("release_session")
    if isinstance(session, dict):
        merged = {**data, **session}
    else:
        merged = data

    snap = merged.get("shared_snapshot")
    has_snap = isinstance(snap, dict) and bool(
        snap.get("ticket_keys") or snap.get("selected_ticket_keys")
    )

    return {
        "snapshot": has_snap,
        "release_notes": bool(
            merged.get("shared_docx_generated")
            or merged.get("rn_extracted")
            or merged.get("rn_change_rows")
        ),
        "sharepoint": bool(
            (merged.get("shared_sharepoint_url") or merged.get("stk_sharepoint") or "").strip()
        ),
        "service_ticket": bool(
            merged.get("stk_created_key")
            or merged.get("stk_summary")
            or merged.get("stk_description_adf")
        ),
        "slack": bool(
            merged.get("stk_slack_sent")
            or merged.get("stk_slack_skipped")
            or merged.get("stk_slack_results")
            or merged.get("stk_slack_body_overrides")
        ),
        "teams": bool(
            merged.get("shared_teams_review_event_id")
            or merged.get("shared_teams_deployment_event_id")
        ),
        "deploy": bool(
            merged.get("wiz_filled")
            or merged.get("wiz_deploy_selected_keys")
            or merged.get("wiz_release")
        ),
    }


def platform_recovery_snapshot(state: dict[str, Any]) -> RecoverySnapshot:
    """Build recovery snapshot from Platform session-like mapping."""
    payload = deploy_draft.build_draft_from_mapping(state)
    extra = release_session._extract_extra(state)  # noqa: SLF001
    if extra:
        payload["release_session"] = extra
    domains = _domain_flags_from_mapping(payload)
    missing = [key for key in PLATFORM_RECOVERY_KEYS if key in state and key not in payload and key not in extra]
    return RecoverySnapshot(domains=domains, missing_keys=missing)


def wizard_recovery_snapshot(session: dict[str, Any]) -> RecoverySnapshot:
    """Build recovery snapshot from MCP wizard session JSON."""
    artifacts = session.get("artifacts") or {}
    drafts = session.get("drafts") or {}
    inputs = session.get("inputs") or {}

    pseudo: dict[str, Any] = {
        "shared_snapshot": artifacts.get("ticket_snapshot"),
        "shared_sharepoint_url": artifacts.get("sharepoint_url"),
        "shared_docx_generated": bool(artifacts.get("release_notes_docx")),
        "stk_created_key": (artifacts.get("service_ticket") or {}).get("key"),
        "stk_slack_sent": (artifacts.get("slack") or {}).get("status") == "sent",
        "stk_slack_skipped": inputs.get("slack_decision") == "skip",
        "stk_slack_results": artifacts.get("slack"),
        "wiz_filled": drafts.get("deployment_info"),
        "wiz_release": inputs.get("version_name"),
    }
    rn_draft = drafts.get("release_notes") or {}
    if rn_draft:
        pseudo["rn_extracted"] = rn_draft.get("extracted")
        pseudo["rn_change_rows"] = rn_draft.get("change_rows")

    stk_draft = drafts.get("service_ticket") or {}
    if stk_draft:
        pseudo["stk_summary"] = stk_draft.get("summary")
        pseudo["stk_description_adf"] = stk_draft.get("description_adf")

    teams_review = artifacts.get("teams_review_meeting") or {}
    teams_deploy = artifacts.get("teams_deployment_meeting") or {}
    if teams_review.get("event_id"):
        pseudo["shared_teams_review_event_id"] = teams_review["event_id"]
    if teams_deploy.get("event_id"):
        pseudo["shared_teams_deployment_event_id"] = teams_deploy["event_id"]

    domains = _domain_flags_from_mapping(pseudo)
    return RecoverySnapshot(domains=domains)


def recovery_parity_ok(platform: RecoverySnapshot, wizard: RecoverySnapshot) -> bool:
    """True when both surfaces report the same domain readiness flags."""
    return platform.domains == wizard.domains


__all__ = [
    "PLATFORM_RECOVERY_KEYS",
    "RECOVERY_DOMAINS",
    "RecoverySnapshot",
    "platform_recovery_snapshot",
    "recovery_parity_ok",
    "wizard_recovery_snapshot",
]
