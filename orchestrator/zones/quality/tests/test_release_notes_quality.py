"""Tests for release-notes quality builders (highlights, dashboards, clients)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.release_notes_quality import (
    DEFAULT_ANALYZE_CLIENTS_BULLET,
    assess_release_notes_quality,
    build_custom_clients_list,
    build_dashboard_lines,
    build_key_highlight_lines,
    canonical_client_name,
    clean_release_text,
    improve_extracted,
    prepare_change_table_entries,
)
from jira_client import extract_ticket_info


def _ticket(type_: str, client: str, report: str, description: str, ticket: str = "X-1") -> dict:
    return {
        "type": type_,
        "client": client,
        "report": report,
        "description": description,
        "ticket": ticket,
    }


class TestCleanReleaseText:
    def test_fixes_montly_typo(self):
        assert "Monthly" in clean_release_text("Montly  Report Change")

    def test_fixes_pagianted_typo(self):
        assert "paginated" in clean_release_text("New Pagianted Report").lower()
        assert "pagianted" not in clean_release_text("New Pagianted Report").lower()

    def test_collapses_double_spaces(self):
        assert clean_release_text("Montly  Report") == "Monthly Report"

    def test_adds_space_before_paren(self):
        assert "reports (New" in clean_release_text("reports(New Paginated Report)")


class TestExtractTicketInfoImprovements:
    def test_strips_analyze_prefix_from_report(self):
        info = extract_ticket_info(
            "Analyze - Payout Item Details (paginated report) - Add invoice details",
            "AN-100",
        )
        assert info["report"].lower().startswith("payout item details")
        assert "invoice" in info["description"].lower()

    def test_known_client_prefix_splits_fwbc(self, monkeypatch):
        import config

        monkeypatch.setattr(
            config,
            "PROJECTS",
            [{"key": "PIC", "name": "Customize", "multi_client": True, "client_extraction": "title_prefix"}],
        )
        info = extract_ticket_info(
            "FWBC Customize Pulse Report - Minor Reconfiguration Needed",
            "PIC-100",
        )
        assert info["client"] == "FWBC"
        assert "Pulse" in info["report"] or "Customize" in info["report"]
        assert "Minor Reconfiguration" in info["description"]


class TestImproveExtracted:
    def test_repairs_single_letter_analyze_report(self):
        improved = improve_extracted(
            [
                _ticket(
                    "Analyze",
                    "Standard",
                    "E",
                    "agreements by Member - New Paginated Report",
                    "AN-2",
                )
            ]
        )[0]
        assert improved["report"].lower() != "e"
        assert "agreement" in improved["report"].lower()


class TestBuildKeyHighlightLines:
    def test_screenshot_release_quality(self):
        extracted = [
            _ticket("Custom", "Jetts", "Custom model dataset replacing with Jetts Dataset",
                    "Custom model dataset replacing with Jetts Dataset", "PIC-1"),
            _ticket("Custom", "Jazzercise", "Active Memberships (inc trials)",
                    "New Paginated report", "PIC-3"),
            _ticket("Custom", "Jazzercise", "Course offering by location",
                    "New paginated report", "PIC-4"),
            _ticket("Custom", "Jetts", "Montly  Report Change the Model pointing to custom standard model",
                    "Montly  Report Change the Model pointing to custom standard model", "PIC-6"),
            _ticket("Custom", "FWBC Customize Pulse Report", "Minor Reconfiguration Needed",
                    "Minor Reconfiguration Needed", "PIC-8"),
            _ticket("Analyze", "Standard", "Promo look up", "New Pagianted Report", "AN-1"),
            _ticket("Analyze", "Standard", "E",
                    "agreements by Member - New Paginated Report", "AN-2"),
            _ticket("Analyze", "Standard", "Analyze",
                    "Payout Item Details (paginated report) - Add invoice details", "AN-4"),
        ]
        lines = build_key_highlight_lines(extracted)
        text = "\n".join(lines)

        assert "Montly" not in text
        assert "Monthly" in text
        assert "Pagianted" not in text
        assert "FWBC:" in text
        assert "FWBC Customize Pulse Report:" not in text
        assert "Updates to E:" not in text
        assert "Updates to Analyze:" not in text
        assert "Standard (Analyze): Updates to Promo look up" in text
        assert any(line.startswith("Jazzercise:") for line in lines)
        assert any(line.startswith("Jetts:") for line in lines)

    def test_dedupes_identical_bodies(self):
        extracted = [
            _ticket("Custom", "Jetts", "Trends Report", "Trends Report", "PIC-1"),
            _ticket("Custom", "Jetts", "Trends Report", "Trends Report", "PIC-2"),
        ]
        lines = build_key_highlight_lines(extracted)
        assert lines == ["Jetts: Trends Report"]


class TestBuildDashboardLines:
    def test_uses_spaced_analyze_dash_and_repairs_stubs(self):
        extracted = [
            _ticket("Analyze", "Standard", "E",
                    "agreements by Member - New Paginated Report", "AN-2"),
            _ticket("Analyze", "Standard", "Analyze",
                    "Payout Item Details (paginated report) - Add invoice details", "AN-4"),
            _ticket("Custom", "Jetts", "Montly  Report Change the Model pointing to custom standard model",
                    "Montly  Report Change the Model pointing to custom standard model", "PIC-6"),
            _ticket("Custom", "Jazzercise", "Active Memberships (inc trials)",
                    "New Paginated report", "PIC-3"),
        ]
        lines = build_dashboard_lines(extracted)
        text = "\n".join(lines)

        assert "Analyze- E" not in text
        assert "Analyze- Analyze" not in text
        assert "Analyze -" in text
        assert "Montly" not in text
        assert any(line.startswith("Jetts -") for line in lines)
        assert any(line.startswith("Jazzercise -") for line in lines)

    def test_consolidates_same_dashboard(self):
        extracted = [
            _ticket("Analyze", "Standard", "New Members", "add join type filter", "AN-1"),
            _ticket("Analyze", "Standard", "New Members", "fix currency display", "AN-2"),
        ]
        lines = build_dashboard_lines(extracted)
        assert len([ln for ln in lines if "New Members" in ln]) == 1


class TestPrepareChangeTableEntries:
    def test_repairs_weak_report_and_canonical_client(self):
        extracted = [
            _ticket(
                "Analyze",
                "Standard",
                "E",
                "agreements by Member - New Paginated Report",
                "AN-2",
            ),
            _ticket(
                "Analyze",
                "Standard",
                "Analyze",
                "Payout Item Details (paginated report) - Add invoice details",
                "AN-4",
            ),
            _ticket(
                "Custom",
                "XtremeFitness",
                "Custom semantic model optimization",
                "Custom semantic model optimization",
                "PIC-1",
            ),
            _ticket(
                "Custom",
                "FWBC Customize Pulse Report",
                "Minor Reconfiguration Needed",
                "Minor Reconfiguration Needed",
                "PIC-8",
            ),
        ]
        for i, e in enumerate(extracted):
            e["sno"] = str(i + 1)
            e["link"] = f"https://example/{e['ticket']}"
            e["parent_epic"] = e["ticket"]

        rows = prepare_change_table_entries(
            extracted,
            test_by_names=["Mona", "Navya", "Narasimha", "Soumya"],
        )
        by_ticket = {r["ticket"]: r for r in rows}

        assert by_ticket["AN-2"]["report"].lower() != "e"
        assert "agreement" in by_ticket["AN-2"]["report"].lower()
        assert by_ticket["AN-4"]["report"].lower().startswith("payout item details")
        assert by_ticket["PIC-1"]["client"] == "Xtreme Fitness"
        assert by_ticket["PIC-8"]["client"] == "FWBC"
        assert "Pulse" in by_ticket["PIC-8"]["report"]
        assert by_ticket["AN-2"]["test_by"] == "Mona"
        assert by_ticket["PIC-1"]["client"] != "XtremeFitness"

    def test_preserves_order_and_links(self):
        extracted = [
            {
                **_ticket("Custom", "Jetts", "Monthly Report", "model change", "PIC-9"),
                "sno": "1",
                "link": "https://jira/PIC-9",
                "parent_epic": "PIC-4000",
            },
        ]
        rows = prepare_change_table_entries(extracted, test_by_names=["Rekha"])
        assert len(rows) == 1
        assert rows[0]["link"] == "https://jira/PIC-9"
        assert rows[0]["parent_epic"] == "PIC-4000"
        assert rows[0]["test_by"] == "Rekha"

    def test_normalizes_missing_space(self):
        assert canonical_client_name("XtremeFitness") == "Xtreme Fitness"

    def test_normalizes_apostrophe(self):
        assert canonical_client_name("Jett's") == "Jetts"

    def test_normalizes_extra_space(self):
        assert canonical_client_name("Chin Music") == "ChinMusic"

    def test_leaves_unknown_names_alone(self):
        assert canonical_client_name("Acme Gyms") == "Acme Gyms"

    def test_blank_returns_blank(self):
        assert canonical_client_name("") == ""


class TestCustomClientsList:
    def test_canonicalizes_display_names(self):
        extracted = [
            _ticket("Custom", "XtremeFitness", "Sales League", "price review", "PIC-1"),
            _ticket("Custom", "Jett's", "Monthly Report", "model change", "PIC-2"),
        ]
        assert build_custom_clients_list(extracted) == ["Jetts", "Xtreme Fitness"]

    def test_prefers_known_client_over_report_title(self):
        extracted = [
            _ticket(
                "Custom",
                "FWBC Customize Pulse Report",
                "Minor Reconfiguration Needed",
                "Minor Reconfiguration Needed",
                "PIC-8",
            ),
            _ticket("Custom", "Jetts", "Monthly Report", "model change", "PIC-1"),
        ]
        clients = build_custom_clients_list(extracted)
        assert clients == ["FWBC", "Jetts"]


class TestQualityAssessment:
    def test_flags_weak_analyze_and_typos(self):
        warnings = assess_release_notes_quality(
            highlight_lines=["Standard (Analyze): Updates to E: agreements"],
            dashboard_lines=["Analyze- Promo look up", "Jetts - Montly Report"],
            analyze_clients="Analyze clients",
            custom_clients=["FWBC Customize Pulse Report"],
        )
        assert warnings
        assert any("typo" in w.lower() or "Montly" in w for w in warnings)
        assert any("All Analyze-based" in w for w in warnings)
        assert DEFAULT_ANALYZE_CLIENTS_BULLET
