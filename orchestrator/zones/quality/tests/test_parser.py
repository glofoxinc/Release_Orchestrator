"""Tests for the deployment input parser and related helpers in jira_client."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")

from jira_client import (
    _is_only_date_or_time,
    _normalize_client_groups,
    _parse_date,
    _parse_time,
    extract_client_name,
    fuzzy_match_client,
    parse_deployment_input,
)

# ── _parse_date ──────────────────────────────────────────────────────

class TestParseDate:
    def test_slash_mmddyy(self):
        assert _parse_date("04/10/26") == "April 10 2026"

    def test_slash_ddmm_day_gt_12(self):
        assert _parse_date("14/04/26") == "April 14 2026"

    def test_slash_full_year(self):
        assert _parse_date("04/14/2026") == "April 14 2026"

    def test_dash_iso(self):
        assert _parse_date("2026-04-14") == "April 14 2026"

    def test_named_month(self):
        assert _parse_date("April 14, 2026") == "April 14 2026"

    def test_named_month_no_comma(self):
        assert _parse_date("January 5 2025") == "January 05 2025"

    def test_no_date(self):
        assert _parse_date("hello world") is None

    def test_empty(self):
        assert _parse_date("") is None

    def test_ambiguous_both_le12_prefers_mmdd(self):
        result = _parse_date("03/07/26")
        assert result == "March 07 2026"


# ── _parse_time ──────────────────────────────────────────────────────

class TestParseTime:
    def test_12h_colon(self):
        assert _parse_time("10:39 AM IST") == "10:39 AM IST"

    def test_12h_space_separator(self):
        result = _parse_time("10 54AM")
        assert result is not None
        assert "10:54" in result
        assert "AM" in result

    def test_12h_pm(self):
        result = _parse_time("8:23 PM")
        assert result is not None
        assert "8:23 PM" in result

    def test_24h(self):
        result = _parse_time("14:30")
        assert result is not None
        assert "2:30 PM" in result

    def test_24h_with_tz(self):
        result = _parse_time("14:30 UTC")
        assert result == "2:30 PM UTC"

    def test_no_time(self):
        assert _parse_time("no time here") is None

    def test_empty(self):
        assert _parse_time("") is None


# ── _is_only_date_or_time ───────────────────────────────────────────

class TestIsOnlyDateOrTime:
    def test_empty_line(self):
        assert _is_only_date_or_time("") is True

    def test_pure_date(self):
        assert _is_only_date_or_time("04/14/26") is True

    def test_date_and_time(self):
        assert _is_only_date_or_time("14/04/26, 10:39") is True

    def test_client_name(self):
        assert _is_only_date_or_time("Jetts") is False

    def test_uuid_line(self):
        assert _is_only_date_or_time("a4438257-1820-44e0-8639-efb05911871f") is True

    def test_client_with_date(self):
        assert _is_only_date_or_time("Xtreme: 04/10/26, 8:23 PM") is False


# ── extract_client_name ─────────────────────────────────────────────

class TestExtractClientName:
    def test_dash_separator(self):
        assert extract_client_name("Jetts - Monthly report") == "Jetts"

    def test_em_dash(self):
        assert extract_client_name("XPO — Dashboard update") == "XPO"

    def test_en_dash(self):
        assert extract_client_name("Jazz – Fix data") == "Jazz"

    def test_no_separator(self):
        assert extract_client_name("standalone ticket") == "Unknown"

    def test_empty(self):
        assert extract_client_name("") == "Unknown"


# ── _normalize_client_groups ────────────────────────────────────────

class TestNormalizeClientGroups:
    def test_merges_prefix(self):
        groups = {
            "Jetts": [{"key": "PIC-1"}],
            "Jetts Monthly report": [{"key": "PIC-2"}],
        }
        result = _normalize_client_groups(groups)
        assert "Jetts" in result
        assert "Jetts Monthly report" not in result
        assert len(result["Jetts"]) == 2

    def test_no_merge_needed(self):
        groups = {
            "Jetts": [{"key": "PIC-1"}],
            "XPO": [{"key": "PIC-2"}],
        }
        result = _normalize_client_groups(groups)
        assert len(result) == 2

    def test_empty(self):
        assert _normalize_client_groups({}) == {}


# ── fuzzy_match_client ──────────────────────────────────────────────

class TestFuzzyMatchClient:
    def test_exact(self):
        assert fuzzy_match_client("Jetts", ["Jetts", "XPO"]) == "Jetts"

    def test_case_insensitive(self):
        assert fuzzy_match_client("jetts", ["Jetts", "XPO"]) == "Jetts"

    def test_substring_no_longer_matches_loosely(self):
        assert fuzzy_match_client("xpo dataset", ["XPO", "Jetts"]) is None

    def test_prefix_typo(self):
        assert fuzzy_match_client("jets", ["Jetts", "XPO"]) == "Jetts"

    def test_no_match(self):
        assert fuzzy_match_client("Unknown", ["Jetts", "XPO"]) is None

    def test_empty_input(self):
        assert fuzzy_match_client("", ["Jetts"]) is None

    def test_short_substring_does_not_match(self):
        assert fuzzy_match_client("BD", ["BDGyms", "Jetts"]) is None

    def test_space_insensitive_match(self):
        assert fuzzy_match_client("BD Gyms", ["BDGyms", "Jetts"]) == "BDGyms"
        assert fuzzy_match_client("bd  gyms", ["BDGyms"]) == "BDGyms"

    def test_xtreme_fitness_with_space(self):
        clients = ["Xtreme Fitness", "Jetts"]
        assert fuzzy_match_client("Xtreme Fitness", clients) == "Xtreme Fitness"
        assert fuzzy_match_client("Xtreme  Fitness", clients) == "Xtreme Fitness"


# ── parse_deployment_input (integration) ────────────────────────────

class TestParseDeploymentInput:
    SAMPLE = (
        "jets -- deploymentID - decdd8a9-e00a-49d5-b6bd-1275d713d7af\n"
        "10:39 AM\n"
        "XPO Deployment ID: 6092dd73-8413-4b8a-b59e-86ef12a0a89f\n"
        "10 54AM\n"
        "xpo dataset refresh initiated\n"
        "jazz Deployment ID: a4438257-1820-44e0-8639-efb05911871f\n"
        "14/04/26, 10:39\n"
        "Xtreme: 04/10/26, 8:23 PM\n"
        "Deployment ID: d0d7442d-a9f3-4b5f-a954-7b12d2209fa5\n"
        "Lift: 04/14/26, 11:29 AM\n"
        "Deployment ID: 091c3783-0716-4e3c-ae80-030f555b6aac\n"
    )

    def test_finds_all_uuids(self):
        results = parse_deployment_input(self.SAMPLE)
        assert len(results) == 5

    def test_client_names_detected(self):
        results = parse_deployment_input(self.SAMPLE)
        clients = [r.client.lower() for r in results]
        assert "jets" in clients[0]
        assert "xpo" in clients[1].lower()
        assert "jazz" in clients[2].lower()
        assert "xtreme" in clients[3].lower()
        assert "lift" in clients[4].lower()

    def test_xtreme_date_is_april(self):
        results = parse_deployment_input(self.SAMPLE)
        xtreme = [r for r in results if "xtreme" in r.client.lower()][0]
        assert "April" in xtreme.deployment_date

    def test_times_detected(self):
        results = parse_deployment_input(self.SAMPLE)
        for r in results:
            assert r.deployment_time, f"No time detected for {r.client}"

    def test_simple_single_block(self):
        raw = "Deployment ID: a4438257-1820-44e0-8639-efb05911871f\n14/04/26, 10:39"
        results = parse_deployment_input(raw)
        assert len(results) == 1
        assert results[0].deployment_id == "a4438257-1820-44e0-8639-efb05911871f"
        assert "April" in results[0].deployment_date
        assert results[0].deployment_time

    def test_empty_input(self):
        assert parse_deployment_input("") == []
        assert parse_deployment_input("   \n\n  ") == []

    def test_text_without_uuid(self):
        assert parse_deployment_input("Jetts deployed at 10:39 AM\nno uuid here") == []


class TestMatchDeploymentsToTickets:
    def test_bd_gyms_with_space_matches_bdgyms(self):
        from jira_client import match_deployments_to_tickets

        raw = (
            "BD Gyms Deployment ID: 67cc3b81-ef6f-438b-9bb4-1b2913152fb2\n"
            "07/01/26, 10:55 AM"
        )
        parsed = parse_deployment_input(raw)
        grouped = {
            "BDGyms": [{"key": "PIC-5638", "fields": {"summary": "BDGyms - Report"}}],
            "Jetts": [{"key": "PIC-1", "fields": {}}],
        }
        matched = match_deployments_to_tickets(parsed, grouped)
        assert len(matched) == 1
        assert matched[0].matched_jira_client == "BDGyms"
        assert matched[0].ticket_keys == ["PIC-5638"]
        assert not matched[0].error
