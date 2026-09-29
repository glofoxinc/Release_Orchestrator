"""Single registry for session persistence keys (Platform + MCP + tests)."""

from __future__ import annotations

import deploy_draft

# Re-export from session_persist until full migration completes.
from session_persist import RELEASE_NOTES_PERSIST_KEYS, SERVICE_TICKET_PERSIST_KEYS

_RELEASE_SESSION_CORE: tuple[str, ...] = (
    "shared_teams_review_event_id",
    "shared_teams_deployment_event_id",
    "shared_teams_review_url",
    "shared_teams_deployment_url",
    "shared_teams_review_web",
    "shared_teams_deployment_web",
    "stk_slack_body_overrides",
    "stk_slack_version",
    "stk_slack_deploy_date",
    "stk_slack_sharepoint",
    "stk_planned_start_date",
    "stk_planned_start_time",
    "stk_planned_end_date",
    "stk_planned_end_time",
    "stk_schedule_tz",
    "stk_change_type",
    "shared_snapshot",
    "tr_grouped",
    "tr_selected_keys",
    "tr_step",
    "tr_selection_mode",
    "tr_issues_fp",
    "stk_created_key",
    "stk_created_url",
    "stk_slack_sent",
    "stk_slack_skipped",
    "stk_slack_results",
    "shared_sharepoint_url",
    "shared_docx_generated",
    "shared_docx_filename",
    "rn_version",
    "rn_date",
    "rn_summary_p1",
    "rn_summary_p2",
    "rn_change_rows",
    "rn_deployment_rows",
    "rn_excluded_tickets",
    "qa_excluded_keys",
    "rn_step",
    "rn_source_fp",
    "rn_issues_fp",
    "rn_step2_loaded",
    "tr_step2_loaded",
    "stk_step",
    "rn_selection_mode",
    "stk_selection_mode",
    "rn_selected_keys",
    "rn_all_extracted",
    "active_app",
    "rn_locked_ticket_source",
    "stk_locked_ticket_source",
    "tr_locked_ticket_source",
    "tr_source_fp",
    "shared_rn_standalone_mode",
    "shared_stk_standalone_mode",
    "shared_deployer_standalone_mode",
    "shared_jira_teams_locked",
    "shared_jira_teams_locked_values",
)

PLATFORM_RECOVERY_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys(
        deploy_draft.PERSIST_KEYS
        + _RELEASE_SESSION_CORE
        + RELEASE_NOTES_PERSIST_KEYS
        + SERVICE_TICKET_PERSIST_KEYS
        + (
            "wiz_undo_data",
            "stk_description_adf",
            "stk_impl_plan",
            "stk_test_plan",
            "stk_backout_plan",
            "stk_business_impact",
            "stk_extracted",
            "stk_approvers",
            "stk_approver_groups",
            "stk_approver_validation",
        )
    )
)

__all__ = [
    "PLATFORM_RECOVERY_KEYS",
    "RELEASE_NOTES_PERSIST_KEYS",
    "SERVICE_TICKET_PERSIST_KEYS",
]
