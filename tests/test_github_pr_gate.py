"""GitHub PR gate — repo map, open PR detection, Jira assignee comments."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import github_host_repo
import github_pr_gate


def test_resolve_an_default_repo():
    result = github_host_repo.resolve_report_host_repo(
        jira_key="AN-5516",
        summary="Fix Unique Visits - Visit Analysis",
    )
    assert result["report_host_repo"] == "glofoxinc/gf-insights-fitnessbi"
    assert result["owner"] == "glofoxinc"
    assert result["repo"] == "gf-insights-fitnessbi"


def test_resolve_pic_jetts_repo():
    result = github_host_repo.resolve_report_host_repo(
        jira_key="PIC-6016",
        summary="Jetts - Member Journey - layout update",
    )
    assert result["report_host_repo"] == "glofoxinc/abc-customize-insights-jetts"


def test_pr_needs_attention_open_unapproved():
    pr = {"state": "open", "draft": False, "merged": False, "mergeable": True}
    reviews = {"approved_count": 0, "changes_requested_count": 0, "pending_count": 1}
    needs, reason = github_pr_gate._pr_needs_attention(pr, reviews)
    assert needs is True
    assert reason == "not_approved"


def test_run_pr_gate_finds_blocking_prs():
    extracted = [
        {
            "ticket": "AN-5516",
            "summary": "Visit Analysis fix",
            "assignee": "Dev User",
            "status": "QA(migrated)",
            "project": "AN",
        }
    ]
    fake_prs = [
        {
            "number": 42,
            "title": "AN-5516: fix visits",
            "html_url": "https://github.com/glofoxinc/gf-insights-fitnessbi/pull/42",
            "state": "open",
            "draft": False,
            "needs_attention": True,
            "attention_reason": "not_approved",
            "reviews": {"approved_count": 0},
        }
    ]
    with (
        patch.object(github_pr_gate, "gate_enabled", return_value=True),
        patch.object(github_pr_gate, "github_configured", return_value={"configured": True}),
        patch.object(github_pr_gate, "check_ticket_github_prs") as check,
    ):
        check.return_value = {
            "ticket": "AN-5516",
            "assignee": "Dev User",
            "host_repo": {"report_host_repo": "glofoxinc/gf-insights-fitnessbi"},
            "open_prs": fake_prs,
            "blocking_prs": fake_prs,
        }
        result = github_pr_gate.run_pr_gate(extracted)
    assert result["blocking_count"] == 1
    assert result["tickets_with_blocking_prs"][0]["ticket"] == "AN-5516"


def test_post_pr_comments_dry_run():
    gate = {
        "tickets_with_blocking_prs": [
            {
                "ticket": "AN-5516",
                "assignee": "Dev User",
                "blocking_prs": [{"number": 1, "title": "T", "html_url": "https://x", "attention_reason": "not_approved"}],
                "host_repo": {"report_host_repo": "glofoxinc/gf-insights-fitnessbi"},
            }
        ]
    }
    with (
        patch.object(github_pr_gate, "_recent_pr_comment_exists", return_value=False),
        patch.object(github_pr_gate, "_assignee_account_id", return_value=("acc-1", "Dev User")),
    ):
        out = github_pr_gate.post_pr_comments(gate, dry_run=True)
    assert out["status"] == "ok"
    assert out["posted"][0]["ticket"] == "AN-5516"
    assert out["posted"][0]["dry_run"] is True


def test_build_comment_adf_mentions_assignee():
    body = github_pr_gate.build_pr_comment_adf(
        ticket_key="AN-5516",
        blocking_prs=[
            {
                "number": 7,
                "title": "Fix",
                "html_url": "https://github.com/x/y/pull/7",
                "attention_reason": "not_approved",
            }
        ],
        host_repo="glofoxinc/gf-insights-fitnessbi",
        assignee_account_id="712020:test",
        assignee_display_name="Dev User",
    )
    content = body.get("content") or []
    first_para = (content[0].get("content") or []) if content else []
    assert any(node.get("type") == "mention" for node in first_para)
