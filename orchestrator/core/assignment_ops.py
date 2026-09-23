"""Headless TCKT assignment verification and one-shot repair."""

from __future__ import annotations

from typing import Any

import config
import jira_client
from diff_engine import extract_ticket_fields


def _value_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return str(value or "")


def verify_assignments(
    issue_key: str,
    expected_approvers: list,
    expected_groups: list,
    *,
    expected_team: Any = None,
    expected_assignment_group: Any = None,
) -> list[str]:
    """Compare assignment fields on the created ticket with the intended values."""
    mismatches: list[str] = []
    try:
        issue = jira_client.get_issue(issue_key)
        actual = extract_ticket_fields(issue)
    except Exception as exc:  # noqa: BLE001 - verification reports the read error
        return [f"Could not verify assignments: {exc}"]

    expected_approver_ids = {
        str(item.get("accountId") or item.get("account_id") or "")
        for item in (expected_approvers or [])
        if isinstance(item, dict)
    } - {""}
    actual_approvers = actual.get("approvers") or []
    if isinstance(actual_approvers, dict):
        actual_approvers = [actual_approvers]
    actual_approver_ids = {
        str(item.get("accountId") or "")
        for item in actual_approvers
        if isinstance(item, dict)
    } - {""}
    if expected_approver_ids and expected_approver_ids != actual_approver_ids:
        mismatches.append(
            f"Approvers mismatch — expected {len(expected_approver_ids)}, "
            f"got {len(actual_approver_ids)} on the ticket."
        )

    expected_group_names = {
        str(item.get("name") if isinstance(item, dict) else item)
        for item in (expected_groups or [])
    } - {""}
    actual_groups = actual.get("approver_groups") or []
    if isinstance(actual_groups, dict):
        actual_groups = [actual_groups]
    actual_group_names = {
        str(item.get("name") or "")
        for item in actual_groups
        if isinstance(item, dict)
    } - {""}
    if expected_group_names and expected_group_names != actual_group_names:
        mismatches.append(
            f"Approver groups mismatch — expected {', '.join(sorted(expected_group_names))}; "
            f"got {', '.join(sorted(actual_group_names)) or 'none'}."
        )

    fields = issue.get("fields") or {}
    team_id = _value_id(expected_team)
    team_field = config.TCKT_FIELDS.get("team", "")
    if team_id and _value_id(fields.get(team_field) if team_field else None) != team_id:
        mismatches.append(f"Team mismatch — expected {team_id}.")

    group_id = _value_id(expected_assignment_group)
    group_field = config.TCKT_FIELDS.get("assignment_group", "")
    if group_id and _value_id(fields.get(group_field) if group_field else None) != group_id:
        mismatches.append(f"Assignment Group mismatch — expected {group_id}.")
    return mismatches


def verify_and_repair(issue_key: str, draft: dict[str, Any]) -> dict[str, Any]:
    """Verify assignments, reapply once on mismatch, then verify again."""
    expected = {
        "approvers": draft.get("approvers") or config.TCKT_DEFAULTS.get("approvers", []),
        "approver_groups": (
            draft.get("approver_groups")
            or config.TCKT_DEFAULTS.get("approver_groups", [])
        ),
        "team": draft.get("team") or config.TCKT_DEFAULTS.get("team"),
        "assignment_group": (
            draft.get("assignment_group")
            or config.TCKT_DEFAULTS.get("assignment_group")
        ),
    }
    warnings = verify_assignments(
        issue_key,
        expected["approvers"],
        expected["approver_groups"],
        expected_team=expected["team"],
        expected_assignment_group=expected["assignment_group"],
    )
    if not warnings:
        return {"status": "verified", "warnings": [], "apply_warnings": []}

    custom_fields = config.TCKT_FIELDS
    fields: dict[str, Any] = {}
    for name in ("approvers", "approver_groups", "team", "assignment_group"):
        field_id = custom_fields.get(name)
        if field_id and expected[name]:
            fields[field_id] = expected[name]
    change_type_field = custom_fields.get("change_type")
    if change_type_field:
        fields[change_type_field] = (
            draft.get("change_type")
            or config.resolve_tckt_select("change_type", "Normal")
        )
    apply_warnings = jira_client.apply_supplemental_tckt_fields(issue_key, fields)
    remaining = verify_assignments(
        issue_key,
        expected["approvers"],
        expected["approver_groups"],
        expected_team=expected["team"],
        expected_assignment_group=expected["assignment_group"],
    )
    return {
        "status": "verified" if not remaining else "warning",
        "initial_warnings": warnings,
        "warnings": remaining,
        "apply_warnings": apply_warnings,
    }
