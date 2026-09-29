"""Tests for diff_engine.diff_tickets()."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

from diff_engine import (
    _adf_to_text,
    _normalize_list,
    diff_dashboards,
    diff_tickets,
    extract_ticket_fields,
)


def _approver(aid, name="X"):
    return {"accountId": aid, "name": name}


def _group(name):
    return {"name": name}


class TestDiffScalar:
    def test_same_summary_is_same(self):
        result = diff_tickets({"summary": "X"}, {"summary": "X"})
        assert result.by_field("summary").status == "same"

    def test_different_summary_is_changed(self):
        result = diff_tickets({"summary": "X"}, {"summary": "Y"})
        assert result.by_field("summary").status == "changed"

    def test_missing_previous_is_added(self):
        result = diff_tickets({"summary": "X"}, {"summary": ""})
        assert result.by_field("summary").status == "added"

    def test_missing_current_is_removed(self):
        result = diff_tickets({"summary": ""}, {"summary": "X"})
        assert result.by_field("summary").status == "removed"


class TestDiffApprovers:
    def test_same_approvers_is_same(self):
        curr = {"approvers": [_approver("a1"), _approver("a2")]}
        prev = {"approvers": [_approver("a1"), _approver("a2")]}
        fd = diff_tickets(curr, prev).by_field("approvers")
        assert fd.status == "same"

    def test_added_approver(self):
        curr = {"approvers": [_approver("a1"), _approver("a2"), _approver("a3")]}
        prev = {"approvers": [_approver("a1"), _approver("a2")]}
        fd = diff_tickets(curr, prev).by_field("approvers")
        assert fd.status == "added"
        assert fd.added == ["a3"]
        assert fd.removed == []

    def test_removed_approver(self):
        curr = {"approvers": [_approver("a1")]}
        prev = {"approvers": [_approver("a1"), _approver("a2")]}
        fd = diff_tickets(curr, prev).by_field("approvers")
        assert fd.status == "removed"
        assert fd.removed == ["a2"]

    def test_changed_approvers(self):
        curr = {"approvers": [_approver("a1"), _approver("a3")]}
        prev = {"approvers": [_approver("a1"), _approver("a2")]}
        fd = diff_tickets(curr, prev).by_field("approvers")
        assert fd.status == "changed"
        assert fd.added == ["a3"]
        assert fd.removed == ["a2"]


class TestDiffApproverGroups:
    def test_added_group(self):
        fd = diff_tickets(
            {"approver_groups": [_group("A"), _group("B")]},
            {"approver_groups": [_group("A")]},
        ).by_field("approver_groups")
        assert fd.added == ["B"]


class TestRichFields:
    def test_plain_string_description_equal(self):
        curr = {"description": "hello"}
        prev = {"description": "hello"}
        assert diff_tickets(curr, prev).by_field("description").status == "same"

    def test_adf_vs_string_equivalent(self):
        prev_adf = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "hello"}]}
        ]}
        fd = diff_tickets({"description": "hello"}, {"description": prev_adf}).by_field("description")
        assert fd.status == "same"

    def test_different_adf_is_changed(self):
        prev_adf = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "old"}]}
        ]}
        fd = diff_tickets({"description": "new"}, {"description": prev_adf}).by_field("description")
        assert fd.status == "changed"

    def test_adf_to_text_bullets(self):
        adf = {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "item"}]}
            ]}
        ]}
        assert "item" in _adf_to_text(adf)


class TestDiffResult:
    def test_has_changes_only_when_non_same(self):
        assert not diff_tickets({"summary": "X"}, {"summary": "X"}).has_changes()
        assert diff_tickets({"summary": "X"}, {"summary": "Y"}).has_changes()

    def test_to_dict_roundtrip(self):
        d = diff_tickets({"summary": "X"}, {"summary": "Y"}).to_dict()
        assert d["fields"][0]["status"] == "changed"

    def test_changes_returns_only_diffs(self):
        r = diff_tickets({"summary": "a", "priority": "p"}, {"summary": "a", "priority": "q"})
        assert all(f.status != "same" for f in r.changes())
        assert len(r.changes()) == 1


class TestNested:
    def test_dashboards_diff(self):
        curr = {"extracted": [{"type": "Analyze", "client": "Standard", "report": "A"}]}
        prev = {"extracted": [
            {"type": "Analyze", "client": "Standard", "report": "A"},
            {"type": "Analyze", "client": "Standard", "report": "B"},
        ]}
        fd = diff_dashboards(curr, prev)
        assert fd.removed == ["B"]


class TestExtractTicketFields:
    def test_extract_summary_and_priority(self):
        issue = {"fields": {"summary": "foo", "priority": {"name": "P1"}}}
        out = extract_ticket_fields(issue, field_map={})
        assert out["summary"] == "foo"
        assert out["priority"]["name"] == "P1"

    def test_extract_with_field_map(self):
        issue = {"fields": {"summary": "foo", "customfield_11752": [{"accountId": "x"}]}}
        out = extract_ticket_fields(issue, field_map={"approvers": "customfield_11752"})
        assert out["approvers"][0]["accountId"] == "x"


class TestNormalizeList:
    def test_list_of_strings(self):
        assert _normalize_list(["b", "a"]) == ["a", "b"]

    def test_list_of_dicts_with_account_id(self):
        assert _normalize_list([_approver("z"), _approver("a")], key="accountId") == ["a", "z"]

    def test_empty(self):
        assert _normalize_list(None) == []

    def test_comma_separated_string(self):
        assert _normalize_list("b, a") == ["a", "b"]
