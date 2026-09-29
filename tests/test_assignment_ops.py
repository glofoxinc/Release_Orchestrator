"""Headless assignment verification tests."""

from unittest.mock import patch

import assignment_ops


def test_verify_assignments_accepts_matching_values():
    issue = {
        "fields": {
            "customfield_10700": "team-1",
            "customfield_13073": {"id": "group-1"},
        }
    }
    actual = {
        "approvers": [{"accountId": "user-1"}],
        "approver_groups": [{"name": "Command Center"}],
    }
    with (
        patch("assignment_ops.jira_client.get_issue", return_value=issue),
        patch("assignment_ops.extract_ticket_fields", return_value=actual),
        patch.dict(
            assignment_ops.config.TCKT_FIELDS,
            {"team": "customfield_10700", "assignment_group": "customfield_13073"},
        ),
    ):
        warnings = assignment_ops.verify_assignments(
            "TCKT-1",
            [{"accountId": "user-1"}],
            [{"name": "Command Center"}],
            expected_team="team-1",
            expected_assignment_group={"id": "group-1"},
        )
    assert warnings == []


def test_verify_and_repair_reapplies_once():
    with (
        patch(
            "assignment_ops.verify_assignments",
            side_effect=[["Approvers mismatch"], []],
        ) as verify,
        patch(
            "assignment_ops.jira_client.apply_supplemental_tckt_fields",
            return_value=[],
        ) as apply,
        patch.dict(
            assignment_ops.config.TCKT_FIELDS,
            {
                "approvers": "a",
                "approver_groups": "g",
                "team": "t",
                "assignment_group": "ag",
                "change_type": "ct",
            },
        ),
        patch.dict(
            assignment_ops.config.TCKT_DEFAULTS,
            {
                "approvers": [{"accountId": "user-1"}],
                "approver_groups": [{"name": "Command Center"}],
                "team": "team-1",
                "assignment_group": {"id": "group-1"},
            },
        ),
    ):
        result = assignment_ops.verify_and_repair("TCKT-1", {})
    assert result["status"] == "verified"
    assert verify.call_count == 2
    apply.assert_called_once()
