"""Role notify messages — owners, testers, review, missing fix versions."""

from __future__ import annotations

import outlook_mail
import release_role_notify as rn


def _rows() -> list[dict]:
    return [
        {
            "ticket": "AN-1",
            "summary": "Details country",
            "assignee": "Lakshmi Narasimha",
            "assignee_email": "lakshmi@example.com",
            "link": "https://example/browse/AN-1",
            "fix_versions": ["2026.4.10.15"],
            "test_by": "Rekha",
        },
        {
            "ticket": "PIC-2",
            "summary": "Lift payments",
            "assignee": "Navya Begum",
            "assignee_email": "navya@example.com",
            "link": "https://example/browse/PIC-2",
            "fix_versions": ["2026.4.10.15"],
            "test_by": "Chanti",
        },
    ]


def test_testers_from_notes():
    testers = rn.testers_from_notes(_rows())
    names = {t["name"] for t in testers}
    assert names == {"Rekha", "Chanti"}


def test_owner_and_tester_dry_run():
    out = rn.notify_owners_and_testers(
        _rows(),
        version_name="2026.4.10.15",
        shipit_key="SHIPIT-99",
        owner_name="Lakshmi Narasimha",
        owner_email="lakshmi@example.com",
        dry_run=True,
    )
    assert out["dry_run"] is True
    assert "deployment owner" in out["owner"]["message"].lower()
    assert "SHIPIT-99" in out["owner"]["message"]
    assert len(out["testers"]) == 2
    assert all("tester" in t["message"].lower() for t in out["testers"])
    assert out["owner"]["outlook"]["outlook_mcp_handoff"]["subject"]
    assert "SHIPIT create" in str(out.get("sushma") or "")


def test_sushma_notified_when_shipit_created():
    out = rn.notify_sushma_on_shipit_created(
        _rows(),
        version_name="2026.4.10.15",
        shipit_key="SHIPIT-99",
        dry_run=True,
        sharepoint_url="https://example.sharepoint.com/Release%20Notes%202026.4.10.15.docx",
        client_sharepoint_url="https://example.sharepoint.com/Client%20Release%20Notes%202026.4.10.15.docx",
    )
    assert out["ok"] is True
    assert out["shipit_key"] == "SHIPIT-99"
    assert out["scope"] == "SHIPIT-linked tickets only"
    msg = out["combined"]["message"]
    assert msg.startswith("Release orchestrator:")
    assert out["combined"]["subject"].startswith("Release orchestrator:")
    assert "Sushma" in msg
    assert "SHIPIT-99" in msg
    assert "whenever a SHIPIT is created" in msg
    assert "Release notes:" in msg
    assert "Client notes:" in msg
    assert "this SHIPIT only" in msg
    assert "Fix Versions OK" in out["combined"]["subject"]
    assert out["all_good"] is True
    assert "PIC-4" in msg or "AN-1" in msg
    assert out["combined"]["playwright_handoff"]["steps"]
    blocked = rn.notify_sushma_on_shipit_created(
        _rows(),
        version_name="2026.4.10.15",
        shipit_key="",
        dry_run=True,
    )
    assert blocked["ok"] is False


def test_review_skips_empty_assignee():
    out = rn.notify_review_assignees(
        _rows(),
        version_name="2026.4.10.15",
        when="tomorrow 10:30 IST",
        dry_run=True,
    )
    assert out["skipped"]
    names = {r["name"] for r in out["recipients"]}
    assert "Lakshmi Narasimha" in names
    assert "Rekha" in names
    assert "tomorrow 10:30 IST" in out["recipients"][0]["message"]


def test_classify_past_future_and_blank_fix_versions():
    target = "2026.4.10.15"
    blank = {"ticket": "AN-1", "fix_versions": []}
    past = {"ticket": "PIC-2", "fix_versions": ["2026.4.10.08"]}
    future = {"ticket": "AN-3", "fix_versions": ["2026.4.10.22"]}
    ok = {"ticket": "PIC-4", "fix_versions": ["2026.4.10.15"]}
    assert rn.classify_fix_version(blank, target) == "missing"
    assert rn.classify_fix_version(past, target) == "past"
    assert rn.classify_fix_version(future, target) == "future"
    assert rn.classify_fix_version(ok, target) == "ok"
    out = rn.notify_missing_fix_versions(
        [blank, past, future, ok],
        version_name=target,
        shipit_key="SHIPIT-99",
        dry_run=True,
    )
    assert out["missing_keys"] == ["AN-1"]
    assert out["past_keys"] == ["PIC-2"]
    assert out["future_keys"] == ["AN-3"]
    assert out["ok_keys"] == ["PIC-4"]
    assert out["ok_count"] == 1
    assert out["all_good"] is False
    msg = out["escalation"]["message"]
    assert msg.startswith("Release orchestrator:")
    assert out["escalation"]["subject"].startswith("Release orchestrator:")
    assert "SHIPIT-99" in msg
    assert "Blank" in msg
    assert "Earlier version" in msg
    assert "Later version" in msg
    assert "2026.4.10.08" in msg
    assert "2026.4.10.22" in msg
    assert "PIC-4" in msg
    assert "All good" in msg


def test_all_good_fix_versions_still_mails_sushma():
    rows = [
        {"ticket": "PIC-4", "summary": "Ready", "fix_versions": ["2026.4.10.15"]},
        {"ticket": "AN-5", "summary": "Also ready", "fix_versions": ["2026.4.10.15"]},
    ]
    out = rn.notify_missing_fix_versions(
        rows,
        version_name="2026.4.10.15",
        shipit_key="SHIPIT-99",
        dry_run=True,
    )
    assert out["all_good"] is True
    assert out["ok_keys"] == ["PIC-4", "AN-5"]
    assert out["missing_count"] == 0
    msg = out["escalation"]["message"]
    assert "All good" in msg
    assert "PIC-4" in msg
    assert "AN-5" in msg
    assert "SHIPIT-99" in msg
    assert "Fix Versions OK" in out["escalation"]["subject"]


def test_empty_fix_version_check_still_mails_sushma():
    out = rn.notify_missing_fix_versions(
        [],
        version_name="2026.4.10.15",
        shipit_key="",
        dry_run=True,
    )
    assert out["all_good"] is False
    assert "no tickets" in out["escalation"]["subject"].lower()
    assert "create Fix Version" in out["escalation"]["message"]


def test_missing_fix_versions_escalates():
    rows = _rows()
    rows[0]["fix_versions"] = []
    rows[0]["fix_version"] = ""
    out = rn.notify_missing_fix_versions(rows, version_name="2026.4.10.15", dry_run=True)
    assert out["missing_count"] == 1
    assert "AN-1" in out["missing_keys"]
    assert "Fix Version" in out["escalation"]["message"]
    assert "approve" in out["escalation"]["message"].lower()


def test_developer_reminder_is_only_two_phrases():
    rules = rn.developer_comment_rules()
    assert "ready for review" in rules
    assert "ready for release" in rules
    assert "Jira ticket" in rules
    assert "Fix Version" in rules
    assert "group follow-up" in rules or "Teams group" in rules
    adf = rn.build_developer_reminder_adf(
        {
            "ticket": "AN-1",
            "assignee": "Lakshmi Narasimha",
            "assignee_account_id": "acc-1",
        },
        version_name="2026.4.10.15",
        shipit_key="SHIPIT-99",
    )
    texts = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                texts.append(node.get("text") or "")
            if node.get("type") == "mention":
                assert node["attrs"]["id"] == "acc-1"
            for child in node.get("content") or []:
                walk(child)

    walk(adf)
    blob = "\n".join(texts)
    assert "Release Orchestrator reminder" in blob
    assert "SHIPIT-99" in blob
    assert "AN-1" in blob


def test_remind_shipit_developers_dry_run_skips_existing(monkeypatch):
    comments = {
        "AN-1": [],
        "PIC-2": [{"body": "Release Orchestrator reminder already here"}],
    }
    monkeypatch.setattr(
        "jira_client.get_issue_comments",
        lambda key: comments.get(key, []),
    )
    out = rn.remind_shipit_developers(
        _rows(),
        version_name="2026.4.10.15",
        shipit_key="SHIPIT-99",
        dry_run=True,
    )
    by_key = {r["ticket"]: r for r in out["tickets"]}
    assert by_key["AN-1"]["ok"] is True
    assert by_key["AN-1"]["skipped"] is False
    assert by_key["PIC-2"]["skipped"] is True
    assert out["posted_or_previewed"] == 1


def test_outlook_dry_run_without_graph():
    result = outlook_mail.send_mail(
        to=["sushma@example.com"],
        subject="Fix Version needed",
        body="Please create the version.",
        dry_run=True,
    )
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["to"] == ["sushma@example.com"]
