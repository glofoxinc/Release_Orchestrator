"""Central session persistence — save release state with logging and UI feedback."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Release Notes draft fields worth persisting across restart.
RELEASE_NOTES_PERSIST_KEYS: tuple[str, ...] = (
    "rn_version",
    "rn_date",
    "rn_dev_team",
    "rn_release_owner",
    "rn_senior_mgr",
    "rn_director",
    "rn_svp",
    "rn_environment",
    "rn_extracted",
    "rn_all_extracted",
    "rn_selected_keys",
    "rn_summary_p1",
    "rn_summary_p2",
    "rn_analyze_report_rows",
    "rn_custom_report_tables",
    "rn_custom_clients",
    "rn_change_rows",
    "rn_deployment_rows",
    "rn_delivered_report_rows",
    "rn_excluded_tickets",
    "rn_sanity_checklist",
    "rn_screenshot_names",
    "rn_testing_evidence_tickets",
    "rn_docx_filename",
    "shared_docx_generated",
    "shared_docx_filename",
    "rn_docx_bytes",
)

# Service ticket — post-create and mid-wizard (steps 2–6 survive restart).
SERVICE_TICKET_PERSIST_KEYS: tuple[str, ...] = (
    "stk_created_key",
    "stk_created_url",
    "stk_summary",
    "stk_slack_sent",
    "stk_slack_skipped",
    "stk_slack_results",
    "stk_slack_body_overrides",
    "stk_sharepoint",
    "stk_extracted",
    "stk_issues",
    "stk_description_adf",
    "stk_description_text",
    "stk_description_custom",
    "stk_impl_plan",
    "stk_test_plan",
    "stk_backout_plan",
    "stk_business_impact",
    "stk_approvers",
    "stk_approver_groups",
    "stk_approver_validation",
    "stk_reference_key",
    "stk_change_risk",
    "stk_impact",
    "stk_urgency",
    "stk_plan_extracted_fp",
    "stk_release_fp",
    "stk_issues_fp",
)


def draft_has_restorable_content(draft: dict[str, Any] | None) -> bool:
    """True when a saved draft contains something worth offering restore."""
    if not draft:
        return False
    try:
        from recovery_contract import platform_recovery_snapshot

        if platform_recovery_snapshot(draft).restorable:
            return True
    except Exception:  # noqa: BLE001 - fall back to legacy heuristics
        pass
    if draft.get("release_session"):
        return True
    for key in (
        "wiz_release",
        "wiz_filled",
        "wiz_deploy_selected_keys",
        "stk_created_key",
        "shared_sharepoint_url",
        "stk_sharepoint",
        "shared_snapshot",
    ):
        if draft.get(key) or (key in (draft.get("release_session") or {})):
            return True
    session = draft.get("release_session") or {}
    if session.get("shared_snapshot"):
        return True
    return False


def persist_session(
    state: dict[str, Any],
    *,
    notify: bool = False,
) -> bool:
    """Save release session; return True on success. Optionally toast in Streamlit."""
    try:
        import release_session as rs

        rs.save_release_session(state)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist release session: %s", exc, exc_info=True)
        if notify:
            try:
                import streamlit as st

                st.warning("Could not save release progress to disk — continue carefully.")
            except Exception:  # noqa: BLE001
                pass
        return False


def persist_deploy_draft(state: dict[str, Any], *, notify: bool = False) -> bool:
    """Save session to disk (alias for persist_session — single write path)."""
    return persist_session(state, notify=notify)


__all__ = [
    "RELEASE_NOTES_PERSIST_KEYS",
    "SERVICE_TICKET_PERSIST_KEYS",
    "draft_has_restorable_content",
    "persist_deploy_draft",
    "persist_session",
]
