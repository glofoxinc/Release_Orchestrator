"""Full release workflow persistence — extends deploy_draft for org-wide reuse.

Persists Teams event IDs, Slack draft overrides, TCKT schedule fields, and
deployer state across Streamlit restarts (workspace-scoped, no secrets).
"""

from __future__ import annotations

from typing import Any

import deploy_draft
from session_persist import RELEASE_NOTES_PERSIST_KEYS, SERVICE_TICKET_PERSIST_KEYS

# Additional session keys beyond deploy_draft core.
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
    "tr_selection_mode",
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
)

RELEASE_SESSION_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys(
        _RELEASE_SESSION_CORE + RELEASE_NOTES_PERSIST_KEYS + SERVICE_TICKET_PERSIST_KEYS
    )
)


def save_release_session(state: dict[str, Any]) -> str:
    """Persist deploy draft + release-wide session fields in one file."""
    payload = deploy_draft.build_draft_from_mapping(state)
    extra = _extract_extra(state)
    if extra:
        payload["release_session"] = extra
    has_substance = bool(
        payload.get("wiz_filled")
        or payload.get("wiz_release")
        or payload.get("wiz_deploy_selected_keys")
        or payload.get("stk_created_key")
        or payload.get("shared_sharepoint_url")
        or payload.get("stk_sharepoint")
        or payload.get("release_session")
        or (extra or {}).get("shared_snapshot")
        or (extra or {}).get("stk_extracted")
        or (extra or {}).get("stk_description_adf")
        or (extra or {}).get("rn_extracted")
        or (extra or {}).get("rn_all_extracted")
        or (extra or {}).get("rn_change_rows")
        or (extra or {}).get("rn_version")
        or payload.get("rn_version")
        or payload.get("rn_change_rows")
    )
    path = deploy_draft.draft_path()
    if not has_substance:
        deploy_draft.clear_deploy_draft(path)
        return path
    import json
    import os

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def load_release_session() -> dict[str, Any] | None:
    """Load merged deploy draft + release session extras."""
    draft = deploy_draft.load_deploy_draft()
    if not draft:
        return None
    return draft


def apply_release_session(state: dict[str, Any], draft: dict[str, Any]) -> list[str]:
    """Restore deploy draft and release session keys onto session state."""
    restored = deploy_draft.apply_deploy_draft(state, draft)
    extra = draft.get("release_session")
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key == "tr_selected_keys" and isinstance(value, list):
                state[key] = set(value)
            elif key == "rn_selected_keys" and isinstance(value, list):
                state[key] = set(value)
            elif key == "stk_planned_start_date" and isinstance(value, str):
                from datetime import date

                state[key] = date.fromisoformat(value)
            elif key == "stk_planned_end_date" and isinstance(value, str):
                from datetime import date

                state[key] = date.fromisoformat(value)
            elif key in ("stk_planned_start_time", "stk_planned_end_time") and isinstance(value, str):
                from datetime import datetime

                state[key] = datetime.strptime(value, "%H:%M:%S").time()
            elif key == "stk_slack_deploy_date" and isinstance(value, str):
                from datetime import date

                state[key] = date.fromisoformat(value)
            else:
                state[key] = deploy_draft.deserialize_persisted_value(key, value)
            if key not in restored:
                restored.append(key)
    return restored


def clear_release_session() -> None:
    deploy_draft.clear_deploy_draft()


def _extract_extra(state: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in RELEASE_SESSION_KEYS:
        if key not in state:
            continue
        value = state[key]
        serialized = deploy_draft._serialize_value(value, key=key)  # noqa: SLF001
        if serialized is not None:
            out[key] = serialized
        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()
    for key, value in state.items():
        if str(key).startswith("stk_release_") and isinstance(value, dict):
            serialized = deploy_draft._serialize_value(value, key=key)  # noqa: SLF001
            if serialized is not None:
                out[key] = serialized
            continue
        if not (
            str(key).endswith("_statuses_PIC")
            or str(key).endswith("_statuses_AN")
            or str(key).endswith("_locked_ticket_source")
            or "_jira_teams_" in str(key)
            or key
            in (
                "shared_jira_teams_locked",
                "shared_jira_teams_locked_values",
                "rn_selection_mode",
                "stk_selection_mode",
                "tr_selection_mode",
            )
        ):
            continue
        if isinstance(value, list):
            out[key] = list(value)
        elif key not in out:
            out[key] = value
    return out


__all__ = [
    "RELEASE_SESSION_KEYS",
    "apply_release_session",
    "clear_release_session",
    "load_release_session",
    "save_release_session",
]
