"""Tests for consolidation and the consolidation detector."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

from unittest.mock import patch

import config
import consolidation
import consolidation_detector


def _an(ticket, report, description, client="Standard"):
    return {
        "ticket": ticket,
        "type": "Analyze",
        "client": client,
        "report": report,
        "description": description,
    }


def _pic(ticket, client, report, description):
    return {
        "ticket": ticket,
        "type": "Custom",
        "client": client,
        "report": report,
        "description": description,
    }


class TestDashboardLabel:
    def test_analyze_uses_report(self):
        assert consolidation.dashboard_label(_an("AN-1", "New Members", "fix")) == "New Members"

    def test_custom_joins_client_and_report(self):
        label = consolidation.dashboard_label(_pic("PIC-1", "Jetts", "Revenue", "fix"))
        assert label == "Jetts - Revenue"

    def test_custom_without_report_uses_client(self):
        assert consolidation.dashboard_label(_pic("PIC-1", "Jetts", "", "fix")) == "Jetts"

    def test_falls_back_to_description_when_empty(self):
        assert consolidation.dashboard_label(_an("AN-1", "", "Orphan description")) == "Orphan description"


class TestConsolidateDashboards:
    def test_single_ticket_pass_through(self):
        res = consolidation.consolidate_dashboards([_an("AN-1", "New Members", "fix")])
        assert len(res) == 1
        assert res[0]["label"] == "New Members"
        assert res[0]["summary"] == "fix"
        assert res[0]["refs"] == "AN-1"

    def test_merges_same_dashboard(self):
        tickets = [
            _an("AN-1", "New Members", "Add Join Type filter"),
            _an("AN-2", "New Members", "Fix currency display"),
            _an("AN-3", "New Members", "Standardize visibility"),
        ]
        res = consolidation.consolidate_dashboards(tickets)
        assert len(res) == 1
        assert res[0]["refs"] == "AN-1, AN-2, AN-3"
        assert "join type" in res[0]["summary"].lower()

    def test_description_equals_label_is_skipped(self):
        res = consolidation.consolidate_dashboards([_an("AN-1", "New Members", "New Members")])
        assert res[0]["summary"] == ""

    def test_different_clients_same_report_remain_separate(self):
        tickets = [
            _pic("PIC-1", "Jetts", "Revenue", "fix a"),
            _pic("PIC-2", "Lift", "Revenue", "fix b"),
        ]
        res = consolidation.consolidate_dashboards(tickets)
        assert len(res) == 2
        labels = {r["label"] for r in res}
        assert labels == {"Jetts - Revenue", "Lift - Revenue"}

    def test_empty_input_empty_output(self):
        assert consolidation.consolidate_dashboards([]) == []


class TestDeduplicateByDashboard:
    def test_merges_duplicate_labels(self):
        items = [
            {"label": "New Members", "summary": "fix A", "refs": "AN-1"},
            {"label": "New Members", "summary": "fix B", "refs": "AN-2"},
        ]
        merged = consolidation.deduplicate_by_dashboard(items)
        assert len(merged) == 1
        assert merged[0]["refs"] == "AN-1, AN-2"
        assert "fix A" in merged[0]["summary"]
        assert "fix B" in merged[0]["summary"]

    def test_preserves_order(self):
        items = [
            {"label": "A", "summary": "x", "refs": "1"},
            {"label": "B", "summary": "y", "refs": "2"},
            {"label": "A", "summary": "z", "refs": "3"},
        ]
        merged = consolidation.deduplicate_by_dashboard(items)
        assert [m["label"] for m in merged] == ["A", "B"]
        assert merged[0]["refs"] == "1, 3"

    def test_skips_blank_labels(self):
        merged = consolidation.deduplicate_by_dashboard([
            {"label": "", "summary": "ignored"},
            {"label": "A", "summary": "kept"},
        ])
        assert len(merged) == 1
        assert merged[0]["label"] == "A"

    def test_case_insensitive_summary_dedupe(self):
        items = [
            {"label": "X", "summary": "Fix Bug", "refs": "1"},
            {"label": "X", "summary": "fix bug", "refs": "2"},
        ]
        merged = consolidation.deduplicate_by_dashboard(items)
        summary_lower = merged[0]["summary"].lower()
        assert summary_lower.count("fix bug") == 1


class TestDetectConsolidationOpportunities:
    def _patch_projects(self):
        return patch.object(
            config, "PROJECTS",
            [{"key": "AN", "multi_client": False}, {"key": "PIC", "multi_client": True}],
        )

    def test_two_tickets_same_dashboard_yields_suggestion(self):
        tickets = [
            _an("AN-1", "New Members", "add filter"),
            _an("AN-2", "New Members", "fix currency"),
        ]
        out = consolidation_detector.detect_consolidation_opportunities(tickets)
        labels = {s.label for s in out if s.kind == "dashboard"}
        assert "New Members" in labels

    def test_single_ticket_is_not_suggested(self):
        out = consolidation_detector.detect_consolidation_opportunities([
            _an("AN-1", "New Members", "fix"),
        ])
        assert not any(s.kind == "dashboard" for s in out)

    def test_merged_bullet_matches_rule_format(self):
        tickets = [
            _an("AN-5192", "New Members", "Add Join Type filter"),
            _an("AN-5194", "New Members", "Fix currency display"),
        ]
        out = consolidation_detector.detect_consolidation_opportunities(tickets)
        dashboard = next(s for s in out if s.kind == "dashboard")
        assert dashboard.merged_bullet.startswith("**New Members** – ")
        assert "AN-5192" in dashboard.merged_bullet
        assert "AN-5194" in dashboard.merged_bullet

    def test_client_grouping_when_multiple_dashboards(self):
        tickets = [
            _pic("PIC-1", "Jetts", "Revenue", "fix"),
            _pic("PIC-2", "Jetts", "Attrition", "fix"),
            _pic("PIC-3", "Jetts", "Revenue", "other"),
        ]
        out = consolidation_detector.detect_consolidation_opportunities(tickets)
        kinds = {s.kind for s in out}
        assert "client" in kinds

    def test_accepts_raw_jira_issues(self):
        raw_issues = [
            {"key": "AN-1", "fields": {"summary": "New Members - add join filter"}},
            {"key": "AN-2", "fields": {"summary": "New Members - fix currency"}},
        ]
        with self._patch_projects():
            out = consolidation_detector.detect_consolidation_opportunities(raw_issues)
        assert any(s.label == "New Members" for s in out)

    def test_semantic_similarity_detected(self):
        tickets = [
            {"ticket": "AN-1", "type": "Analyze", "client": "Standard",
             "report": "A", "description": "fix revenue calculation bug"},
            {"ticket": "AN-2", "type": "Analyze", "client": "Standard",
             "report": "B", "description": "fix revenue calculation issue"},
        ]
        out = consolidation_detector.detect_consolidation_opportunities(
            tickets, similarity_threshold=0.5,
        )
        assert any(s.kind == "semantic" for s in out)

    def test_apply_suggestion_collapses_tickets(self):
        tickets = [
            _an("AN-1", "New Members", "add filter"),
            _an("AN-2", "New Members", "fix currency"),
            _an("AN-3", "Revenue Analysis", "other"),
        ]
        out = consolidation_detector.detect_consolidation_opportunities(tickets)
        dashboard = next(s for s in out if s.kind == "dashboard")
        new_list = consolidation_detector.apply_suggestion(tickets, dashboard)
        assert len(new_list) == 2
        merged = new_list[0]
        assert "AN-1" in merged["ticket"] and "AN-2" in merged["ticket"]
        assert merged["description"].startswith("add filter")

    def test_empty_tickets_returns_empty(self):
        assert consolidation_detector.detect_consolidation_opportunities([]) == []

    def test_to_dict_roundtrips(self):
        tickets = [
            _an("AN-1", "A", "x"),
            _an("AN-2", "A", "y"),
        ]
        out = consolidation_detector.detect_consolidation_opportunities(tickets)
        d = out[0].to_dict()
        assert d["label"] == "A"
        assert "AN-1" in d["tickets"]
