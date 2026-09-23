"""Integration tests for the DORA-style deployment dashboard computations."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from release_platform.ui.deployment_dashboard import _build_history_df, _parse_timestamp


def _make_entry(
    *,
    project: str = "PROJ",
    version: str = "1.0.0",
    timestamp: str | None = None,
    success: int = 5,
    errors: int = 0,
    skipped: int = 0,
    ticket_keys: list[str] | None = None,
) -> dict:
    clients: dict = {}
    if ticket_keys:
        clients["default"] = {"tickets": [{"key": k} for k in ticket_keys]}
    entry: dict = {
        "project": project,
        "version": version,
        "success": success,
        "errors": errors,
        "skipped": skipped,
        "clients": clients,
    }
    if timestamp is not None:
        entry["timestamp"] = timestamp
    return entry


def _mock_history(count: int = 7, base_date: datetime | None = None) -> list[dict]:
    base = base_date or datetime(2026, 4, 1, 10, 0, 0)
    entries = []
    for i in range(count):
        ts = base + timedelta(days=i * 2, hours=i)
        tickets = [f"PROJ-{100 + i * 3 + j}" for j in range(3 + (i % 4))]
        entries.append(
            _make_entry(
                project="PROJ" if i % 2 == 0 else "OTHER",
                version=f"1.{i}.0",
                timestamp=ts.isoformat(),
                success=5 + i,
                errors=i % 2,
                ticket_keys=tickets,
            )
        )
    return entries


class TestParseTimestamp:
    def test_valid_iso_string(self):
        result = _parse_timestamp("2026-04-01T10:00:00")
        assert isinstance(result, datetime)
        assert result.year == 2026

    def test_invalid_string_returns_none(self):
        assert _parse_timestamp("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert _parse_timestamp("") is None

    def test_none_returns_none(self):
        assert _parse_timestamp(None) is None


class TestBuildHistoryDf:
    """Verify _build_history_df produces a well-formed DataFrame."""

    def test_returns_dataframe(self):
        df = _build_history_df(_mock_history())
        assert isinstance(df, pd.DataFrame)

    def test_correct_row_count(self):
        history = _mock_history(5)
        df = _build_history_df(history)
        assert len(df) == 5

    def test_columns_present(self):
        df = _build_history_df(_mock_history())
        expected = {
            "timestamp", "project", "version", "success", "errors",
            "skipped", "tickets", "client_count", "day_of_week",
        }
        assert expected.issubset(set(df.columns))

    def test_ticket_count_aggregated(self):
        entry = _make_entry(ticket_keys=["A-1", "A-2", "A-3"])
        df = _build_history_df([entry])
        assert df.iloc[0]["tickets"] == 3

    def test_sorted_by_timestamp(self):
        history = _mock_history(5)
        df = _build_history_df(history)
        timestamps = df["timestamp"].dropna().tolist()
        assert timestamps == sorted(timestamps)


class TestEmptyHistory:
    """Dashboard must handle zero deployments gracefully."""

    def test_empty_list_returns_empty_df(self):
        df = _build_history_df([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_empty_df_columns(self):
        df = _build_history_df([])
        assert len(df.columns) == 0 or df.empty


class TestSingleEntry:
    """A single deployment must not cause divide-by-zero or crash."""

    def test_single_entry_df(self):
        entry = _make_entry(timestamp="2026-04-10T14:30:00", ticket_keys=["X-1"])
        df = _build_history_df([entry])
        assert len(df) == 1

    def test_single_entry_metrics(self):
        entry = _make_entry(timestamp="2026-04-10T14:30:00", ticket_keys=["X-1", "X-2"])
        df = _build_history_df([entry])
        assert df.iloc[0]["tickets"] == 2
        assert df.iloc[0]["success"] == 5

    def test_single_entry_day_of_week(self):
        entry = _make_entry(timestamp="2026-04-10T14:30:00")
        df = _build_history_df([entry])
        assert df.iloc[0]["day_of_week"] == "Friday"


class TestMixedProjectEntries:
    """Verify multi-project history is correctly captured."""

    def test_project_breakdown(self):
        history = _mock_history(6)
        df = _build_history_df(history)
        projects = df["project"].unique().tolist()
        assert "PROJ" in projects
        assert "OTHER" in projects

    def test_per_project_counts(self):
        history = _mock_history(6)
        df = _build_history_df(history)
        proj_counts = df["project"].value_counts()
        assert proj_counts.sum() == 6


class TestMissingTimestamp:
    """Entries without timestamps should still be included."""

    def test_no_timestamp_still_counted(self):
        entry = _make_entry(ticket_keys=["Z-1"])
        entry.pop("timestamp", None)
        df = _build_history_df([entry])
        assert len(df) == 1
        assert pd.isna(df.iloc[0]["timestamp"])
        assert df.iloc[0]["day_of_week"] == "Unknown"

    def test_mixed_timestamped_and_not(self):
        e1 = _make_entry(timestamp="2026-04-05T09:00:00", ticket_keys=["A-1"])
        e2 = _make_entry(ticket_keys=["B-1"])
        e2.pop("timestamp", None)
        df = _build_history_df([e1, e2])
        assert len(df) == 2


class TestLeadTimeCalculation:
    """Verify inter-deployment gap math using raw DataFrame operations."""

    def test_gap_between_two_deployments(self):
        e1 = _make_entry(timestamp="2026-04-01T10:00:00")
        e2 = _make_entry(timestamp="2026-04-03T10:00:00")
        df = _build_history_df([e1, e2])
        ts_sorted = df.sort_values("timestamp")
        gaps = ts_sorted["timestamp"].diff().dropna()
        gap_hours = gaps.dt.total_seconds() / 3600
        assert abs(gap_hours.iloc[0] - 48.0) < 0.01

    def test_average_gap_multiple_entries(self):
        entries = [
            _make_entry(timestamp="2026-04-01T00:00:00"),
            _make_entry(timestamp="2026-04-02T00:00:00"),
            _make_entry(timestamp="2026-04-04T00:00:00"),
        ]
        df = _build_history_df(entries)
        ts_sorted = df.sort_values("timestamp")
        gaps = ts_sorted["timestamp"].diff().dropna()
        gap_hours = gaps.dt.total_seconds() / 3600
        assert abs(gap_hours.mean() - 36.0) < 0.01
