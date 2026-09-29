"""SHIPIT post-create — Review Ready, owner assignee, release ticket links (17036 parity)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shipit_post_create import (
    apply_post_create,
    build_post_create_plan,
    merge_post_create_options,
    release_ticket_keys_from_extracted,
    resolve_owner_account_id,
)


SAMPLE = [{"ticket": "AN-5516", "type": "Analyze", "client": "Standard", "report": "Visits"}]


def test_release_ticket_keys_dedupes():
    rows = [
        {"ticket": "AN-1"},
        {"ticket": "PIC-2"},
        {"ticket": "AN-1"},
    ]
    assert release_ticket_keys_from_extracted(rows) == ["AN-1", "PIC-2"]


def test_build_post_create_plan_prod_steps():
    plan = build_post_create_plan(
        SAMPLE,
        is_test=False,
        owner_account_id="712020:abc",
    )
    assert plan["enabled"] is True
    assert plan["release_ticket_keys"] == ["AN-5516"]
    assert plan["request_type"] == "Manual Change"
    actions = [s["action"] for s in plan["steps"]]
    assert actions == ["assign_to_creator", "transition", "link_release_tickets"]
    assert plan["steps"][-1]["link_type"] == "Discovery - Connected"


def test_build_post_create_plan_skips_test_mode():
    plan = build_post_create_plan(SAMPLE, is_test=True)
    assert plan["enabled"] is False
    assert plan["skipped_reason"] == "test_mode"


def test_merge_post_create_overrides():
    merged = merge_post_create_options({"link_release_tickets": False})
    assert merged["link_release_tickets"] is False
    assert merged["transition_status"] == "Review Ready"


def test_resolve_owner_from_override():
    account_id, _ = resolve_owner_account_id("712020:override")
    assert account_id == "712020:override"


def test_resolve_owner_from_myself():
    with patch("shipit_post_create.jira_client.get_current_user") as mock_user:
        mock_user.return_value = {
            "accountId": "712020:self",
            "displayName": "Test User",
        }
        account_id, name = resolve_owner_account_id(None)
    assert account_id == "712020:self"
    assert name == "Test User"


def test_apply_post_create_happy_path():
    with (
        patch("shipit_post_create.jira_client.set_assignee") as mock_assign,
        patch("shipit_post_create.jira_client.get_issue_status_name", return_value="Open"),
        patch("shipit_post_create.jira_client.transition_to_status", return_value=(True, None)),
        patch("shipit_post_create.jira_client.create_issue_link") as mock_link,
        patch("shipit_post_create._linked_release_keys", return_value=set()),
    ):
        result = apply_post_create(
            "SHIPIT-999",
            SAMPLE,
            is_test=False,
            owner_account_id="712020:owner",
        )

    mock_assign.assert_called_once_with("SHIPIT-999", "712020:owner")
    mock_link.assert_called_once_with("SHIPIT-999", "AN-5516", "Discovery - Connected")
    assert result["status"] == "ok"
    assert len(result["applied"]) == 3


def test_apply_post_create_skips_existing_link():
    with (
        patch("shipit_post_create.jira_client.set_assignee"),
        patch("shipit_post_create.jira_client.get_issue_status_name", return_value="Review Ready"),
        patch("shipit_post_create.jira_client.transition_to_status") as mock_transition,
        patch("shipit_post_create.jira_client.create_issue_link") as mock_link,
        patch("shipit_post_create._linked_release_keys", return_value={"AN-5516"}),
    ):
        result = apply_post_create("SHIPIT-999", SAMPLE, owner_account_id="712020:owner")

    mock_transition.assert_not_called()
    mock_link.assert_not_called()
    assert "already_Review Ready" in result["skipped"]
    assert "link_exists:AN-5516" in result["skipped"]


def test_create_service_ticket_dry_run_includes_post_create_plan():
    from release_mcp import release_ops

    sample = [{
        "ticket": "AN-5516",
        "type": "Analyze",
        "client": "Standard",
        "report": "Visits",
        "description": "Test",
    }]
    result = release_ops.create_service_ticket(
        "2026.3.09.14",
        sharepoint_url="https://example.com/Release%20Notes.docx",
        dry_run=True,
        extracted_override=sample,
    )
    assert result["status"] == "dry_run"
    plan = result.get("post_create_plan") or {}
    assert plan.get("enabled") is True
    assert "AN-5516" in (plan.get("release_ticket_keys") or [])


def test_create_service_ticket_applies_post_create_after_create():
    from release_mcp import release_ops

    sample = [{
        "ticket": "AN-5516",
        "type": "Analyze",
        "client": "Standard",
        "report": "Visits",
        "description": "Test",
    }]

    with (
        patch("jira_client.create_tckt_issue") as mock_create,
        patch("shipit_post_create.apply_post_create") as mock_post,
    ):
        mock_create.return_value = (
            {"key": "SHIPIT-NEW"},
            MagicMock(to_dict=lambda: {"status": "ok"}),
        )
        mock_post.return_value = {"status": "ok", "applied": [{"action": "transition"}]}
        result = release_ops.create_service_ticket(
            "2026.3.09.14",
            sharepoint_url="https://example.com/Release%20Notes.docx",
            dry_run=False,
            extracted_override=sample,
            shipit_owner_account_id="712020:owner",
        )

    mock_post.assert_called_once()
    assert result["key"] == "SHIPIT-NEW"
    assert result["linked_tickets"] == ["AN-5516"]
    assert result["post_create"]["status"] == "ok"
