"""Tests for Change Details Test-by assignment and Testing Status."""

from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.release_notes_test_by import (
    CHANGE_TABLE_TEST_BY_POOL,
    ETL_TEST_BY_NAME,
    assign_change_table_testers,
    assign_change_table_testing_statuses,
    eligible_test_by_candidates,
    is_etl_content,
    is_etl_ticket,
    is_etl_ticket_owner,
    person_name_matches,
    resolve_change_table_test_by,
    resolve_testing_status,
)


class TestPersonNameMatches:
    def test_exact_match(self):
        assert person_name_matches("Navya", "Navya") is True

    def test_first_name_match(self):
        assert person_name_matches("Navya", "Navya Begum") is True
        assert person_name_matches("Narasimha", "Lakshmi Narasimha") is True

    def test_mona_full_name(self):
        assert person_name_matches("Mona", "Ramugalla Mona Sujitha") is True

    def test_no_match(self):
        assert person_name_matches("Mona", "Chanti") is False


class TestEligibleCandidates:
    def test_excludes_ticket_owner(self):
        eligible = eligible_test_by_candidates("Navya Begum")
        assert "Navya" not in eligible
        assert len(eligible) == len(CHANGE_TABLE_TEST_BY_POOL) - 1

    def test_unknown_owner_keeps_full_pool(self):
        eligible = eligible_test_by_candidates("External Contractor")
        assert len(eligible) == len(CHANGE_TABLE_TEST_BY_POOL)


class TestResolveChangeTableTestBy:
    def test_never_matches_owner(self):
        counts = {name: 0 for name in CHANGE_TABLE_TEST_BY_POOL}
        for i in range(20):
            test_by = resolve_change_table_test_by(
                "Chanti",
                ticket_key=f"PIC-{i}",
                row_index=i,
                usage_counts=counts,
            )
            assert not person_name_matches(test_by, "Chanti")
            counts[test_by] = counts.get(test_by, 0) + 1

    def test_least_used_preferred(self):
        counts = {name: 5 for name in CHANGE_TABLE_TEST_BY_POOL}
        counts["Rekha"] = 0
        pick = resolve_change_table_test_by(
            "Mona",
            usage_counts=counts,
        )
        assert pick == "Rekha"


class TestAssignChangeTableTesters:
    def test_one_name_per_entry(self):
        entries = [
            {"ticket": "PIC-1", "assignee": "Alice Dev"},
            {"ticket": "PIC-2", "assignee": "Bob Dev"},
            {"ticket": "PIC-3", "assignee": "Navya"},
        ]
        assigned = assign_change_table_testers(entries, release_seed="rel-1")
        assert len(assigned) == 3
        assert all(name in CHANGE_TABLE_TEST_BY_POOL for name in assigned)
        assert not person_name_matches(assigned[2], "Navya")

    def test_balances_across_pool_for_ten_tickets(self):
        """10 tickets across 9 testers → most get 1, none hog the list."""
        entries = [
            {"ticket": f"PIC-{i}", "assignee": f"Developer {i}"}
            for i in range(10)
        ]
        assigned = assign_change_table_testers(entries)
        counts = Counter(assigned)
        assert len(counts) >= 8
        assert max(counts.values()) <= 2
        assert min(counts.values()) >= 1

    def test_balances_for_twenty_tickets(self):
        entries = [
            {"ticket": f"AN-{i}", "assignee": "Some Dev"}
            for i in range(20)
        ]
        assigned = assign_change_table_testers(entries)
        counts = Counter(assigned)
        assert len(counts) == len(CHANGE_TABLE_TEST_BY_POOL)
        assert max(counts.values()) - min(counts.values()) <= 1

    def test_never_assigns_owner_even_when_balancing(self):
        # Chanti is an in-pool, non-ETL owner — Test by must still skip the owner.
        entries = [
            {"ticket": f"PIC-{i}", "assignee": "Chanti"}
            for i in range(9)
        ]
        assigned = assign_change_table_testers(entries)
        assert "Chanti" not in assigned
        assert all(not person_name_matches(name, "Chanti") for name in assigned)


class TestTestingStatus:
    def test_default_status_blank_until_manual_qa(self):
        assert is_etl_ticket_owner("Ramugalla Mona Sujitha") is True
        assert resolve_testing_status("Mona") == ""
        assert resolve_testing_status("Ramugalla Mona Sujitha") == ""
        assert resolve_testing_status("Navya Begum") == ""
        assert resolve_testing_status("Lakshmi Narasimha") == ""

    def test_batch_statuses_blank(self):
        entries = [
            {"ticket": "PIC-1", "assignee": "Mona"},
            {"ticket": "PIC-2", "assignee": "Chanti"},
            {"ticket": "AN-3", "assignee": "Ramugalla Mona Sujitha"},
        ]
        statuses = assign_change_table_testing_statuses(entries)
        assert statuses == ["", "", ""]


class TestEtlContentDetection:
    def test_bi_reporting_summary_is_etl(self):
        entry = {
            "ticket": "AN-5468",
            "assignee": "Chanti",
            "summary": "Remove Jetts Vasant Square Mall from Fitness BI Reporting",
        }
        assert is_etl_content(entry) is True
        assert is_etl_ticket(entry) is True

    def test_plain_report_ticket_is_not_etl(self):
        entry = {
            "ticket": "AN-10",
            "assignee": "Chanti",
            "summary": "Revenue Report — add month-over-month growth column",
        }
        assert is_etl_content(entry) is False
        assert is_etl_ticket(entry) is False

    def test_explicit_etl_keyword(self):
        entry = {"ticket": "PIC-9", "assignee": "Navya", "report": "ETL nightly load fix"}
        assert is_etl_ticket(entry) is True

    def test_content_etl_ticket_gets_mona_nikhila_and_etl_done(self):
        entries = [
            {
                "ticket": "AN-5468",
                "assignee": "Chanti",
                "summary": "Remove Jetts Vasant Square Mall from Fitness BI Reporting",
            },
            {"ticket": "AN-2", "assignee": "Navya", "summary": "Dashboard tooltip fix"},
        ]
        testers = assign_change_table_testers(entries)
        statuses = assign_change_table_testing_statuses(entries)
        assert testers[0] == ETL_TEST_BY_NAME
        assert statuses[0] == ""
        assert testers[1] != ETL_TEST_BY_NAME
        assert statuses[1] == ""

    def test_mona_owned_ticket_test_by_is_mona_nikhila(self):
        entries = [{"ticket": "PIC-1", "assignee": "Mona Sujitha", "summary": "x"}]
        assert assign_change_table_testers(entries) == [ETL_TEST_BY_NAME]
