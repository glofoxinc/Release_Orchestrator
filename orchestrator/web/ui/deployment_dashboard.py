"""Deployment Dashboard — DORA-style metrics from deployment history."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

import pandas as pd
import streamlit as st

from release_platform.ui.helpers import load_history


def _parse_timestamp(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _build_history_df(history: list[dict]) -> pd.DataFrame:
    """Convert raw history list into a DataFrame with parsed timestamps."""
    records = []
    for h in history:
        ts = _parse_timestamp(h.get("timestamp", ""))
        clients = h.get("clients", {})
        total_tickets = sum(len(c.get("tickets", [])) for c in clients.values())
        records.append(
            {
                "timestamp": ts,
                "project": h.get("project", "Unknown"),
                "version": h.get("version", "?"),
                "success": h.get("success", 0),
                "errors": h.get("errors", 0),
                "skipped": h.get("skipped", 0),
                "tickets": total_tickets,
                "client_count": len(clients),
                "day_of_week": ts.strftime("%A") if ts else "Unknown",
            }
        )
    df = pd.DataFrame(records)
    if not df.empty and df["timestamp"].notna().any():
        df = df.sort_values("timestamp")
    return df


def _render_frequency(df: pd.DataFrame) -> None:
    """Deployment frequency per week and per month with trend."""
    st.markdown("#### Deployment Frequency")

    ts_valid = df.dropna(subset=["timestamp"])
    if ts_valid.empty:
        st.info("No timestamped deployments to chart.")
        return

    ts_valid = ts_valid.copy()
    ts_valid["week"] = ts_valid["timestamp"].dt.to_period("W").dt.start_time
    ts_valid["month"] = ts_valid["timestamp"].dt.to_period("M").dt.start_time

    c1, c2 = st.columns(2)

    with c1:
        weekly = ts_valid.groupby("week").size().reset_index(name="Deployments")
        weekly = weekly.rename(columns={"week": "Week"})
        st.bar_chart(weekly, x="Week", y="Deployments")
        avg_weekly = weekly["Deployments"].mean() if len(weekly) else 0.0
        st.caption(f"Average: **{avg_weekly:.1f}** deployments / week")

    with c2:
        monthly = ts_valid.groupby("month").size().reset_index(name="Deployments")
        monthly = monthly.rename(columns={"month": "Month"})
        st.line_chart(monthly, x="Month", y="Deployments")
        avg_monthly = monthly["Deployments"].mean() if len(monthly) else 0.0
        st.caption(f"Average: **{avg_monthly:.1f}** deployments / month")


def _render_lead_time(df: pd.DataFrame) -> None:
    """Average time between consecutive deployments (proxy for lead time)."""
    st.markdown("#### Lead Time (Inter-Deployment Gap)")

    ts_valid = df.dropna(subset=["timestamp"]).copy()
    if len(ts_valid) < 2:
        st.info("Need at least 2 timestamped deployments to calculate lead time.")
        return

    ts_sorted = ts_valid.sort_values("timestamp")
    gaps = ts_sorted["timestamp"].diff().dropna()
    gap_hours = gaps.dt.total_seconds() / 3600

    avg_gap = gap_hours.mean()
    median_gap = gap_hours.median()
    min_gap = gap_hours.min()
    max_gap = gap_hours.max()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg Gap", f"{avg_gap:.1f}h")
    c2.metric("Median Gap", f"{median_gap:.1f}h")
    c3.metric("Shortest", f"{min_gap:.1f}h")
    c4.metric("Longest", f"{max_gap:.1f}h")


def _render_change_volume(df: pd.DataFrame) -> None:
    """Average tickets per deployment."""
    st.markdown("#### Change Volume")

    if df.empty:
        st.info("No deployment data.")
        return

    total_deploys = len(df)
    total_tickets = int(df["tickets"].sum())
    max_tickets = int(df["tickets"].max()) if total_deploys else 0
    avg_tickets = total_tickets / total_deploys if total_deploys else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg Tickets / Deploy", f"{avg_tickets:.1f}")
    c2.metric("Max Tickets", max_tickets)
    c3.metric("Total Tickets Deployed", total_tickets)
    c4.metric("Total Deployments", total_deploys)

    ts_valid = df.dropna(subset=["timestamp"]).copy()
    if not ts_valid.empty:
        ts_valid["date"] = ts_valid["timestamp"].dt.date
        by_date = ts_valid.groupby("date")["tickets"].sum().reset_index()
        by_date.columns = ["Date", "Tickets"]
        st.bar_chart(by_date, x="Date", y="Tickets")


def _render_by_project(df: pd.DataFrame) -> None:
    """Breakdown of deployments per project key."""
    st.markdown("#### Deployments by Project")

    if df.empty:
        st.info("No deployment data.")
        return

    proj_counts = df["project"].value_counts().reset_index()
    proj_counts.columns = ["Project", "Deployments"]

    c1, c2 = st.columns([1, 2])
    with c1:
        st.dataframe(proj_counts, use_container_width=True, hide_index=True)
    with c2:
        st.bar_chart(proj_counts, x="Project", y="Deployments")


def _render_by_day_of_week(df: pd.DataFrame) -> None:
    """Bar chart showing which days of the week deployments happen."""
    st.markdown("#### Deployments by Day of Week")

    ts_valid = df.dropna(subset=["timestamp"])
    if ts_valid.empty:
        st.info("No timestamped deployments to chart.")
        return

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    counts = Counter(ts_valid["day_of_week"])
    day_df = pd.DataFrame(
        [{"Day": d, "Deployments": counts.get(d, 0)} for d in day_order]
    )

    st.bar_chart(day_df, x="Day", y="Deployments")


def _render_deployments_per_week(df: pd.DataFrame) -> None:
    """Bar chart of deployment count per ISO week."""
    st.markdown("#### Deployments per Week")

    ts_valid = df.dropna(subset=["timestamp"]).copy()
    if ts_valid.empty:
        st.info("No timestamped deployments to chart.")
        return

    ts_valid["week"] = ts_valid["timestamp"].dt.to_period("W").dt.start_time
    weekly = ts_valid.groupby("week").size().reset_index(name="Deployments")
    weekly = weekly.rename(columns={"week": "Week"})
    st.bar_chart(weekly, x="Week", y="Deployments")


def _render_success_rate_trend(df: pd.DataFrame) -> None:
    """Line chart showing rolling success rate over time."""
    st.markdown("#### Success Rate Trend")

    ts_valid = df.dropna(subset=["timestamp"]).copy()
    if ts_valid.empty:
        st.info("No timestamped deployments to chart.")
        return

    ts_valid["total_ops"] = ts_valid["success"] + ts_valid["errors"]
    ts_valid["success_rate"] = ts_valid.apply(
        lambda r: (r["success"] / r["total_ops"] * 100) if r["total_ops"] > 0 else 100.0,
        axis=1,
    )
    ts_valid["week"] = ts_valid["timestamp"].dt.to_period("W").dt.start_time
    weekly_rate = ts_valid.groupby("week")["success_rate"].mean().reset_index()
    weekly_rate.columns = ["Week", "Success Rate (%)"]
    st.line_chart(weekly_rate, x="Week", y="Success Rate (%)")


def _render_avg_duration(history: list[dict]) -> None:
    """Show average deployment duration if start/end timestamps are available."""
    st.markdown("#### Average Deployment Duration")

    durations: list[float] = []
    for h in history:
        start = _parse_timestamp(h.get("timestamp", ""))
        end = _parse_timestamp(h.get("completed_at", ""))
        if start and end and end > start:
            durations.append((end - start).total_seconds() / 60)

    if not durations:
        st.info("Duration data not available. Needs both `timestamp` and `completed_at` in history entries.")
        return

    avg_min = sum(durations) / len(durations)
    min_dur = min(durations)
    max_dur = max(durations)

    c1, c2, c3 = st.columns(3)
    c1.metric("Average", f"{avg_min:.1f} min")
    c2.metric("Shortest", f"{min_dur:.1f} min")
    c3.metric("Longest", f"{max_dur:.1f} min")


def _render_export(df: pd.DataFrame) -> None:
    """Download button for full deployment metrics as CSV."""
    st.markdown("#### Export Dashboard Data")

    export = df.copy()
    if "timestamp" in export.columns and export["timestamp"].notna().any():
        export["timestamp"] = export["timestamp"].apply(
            lambda x: x.isoformat() if pd.notna(x) else ""
        )

    csv_data = export.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CSV",
        data=csv_data,
        file_name="deployment_metrics.csv",
        mime="text/csv",
    )


def _render_recent_table(df: pd.DataFrame, n: int = 10) -> None:
    """Show the last N deployments as a summary table."""
    st.markdown("#### Recent Deployments")

    if df.empty:
        st.info("No deployments yet.")
        return

    recent = df.tail(n).iloc[::-1].copy()
    display = recent[["timestamp", "project", "version", "tickets", "success", "errors"]].copy()
    display.columns = ["Timestamp", "Project", "Version", "Tickets", "Updated", "Errors"]

    if display["Timestamp"].notna().any():
        display["Timestamp"] = display["Timestamp"].apply(
            lambda x: x.strftime("%d %b %Y, %I:%M %p") if pd.notna(x) else "\u2014"
        )

    st.dataframe(display, use_container_width=True, hide_index=True)


def render_deployment_dashboard() -> None:
    """Main entry point — renders the full DORA-style deployment dashboard."""
    st.caption(
        "DORA-style metrics derived from your deployment history — "
        "frequency, lead time, change volume, and success rate."
    )
    history = load_history()

    if not history:
        st.info("No deployment data yet. Deploy a release to start tracking metrics.")
        return

    df = _build_history_df(history)

    if df.empty:
        st.info("Deployment history could not be parsed. Check history file format.")
        return

    _render_change_volume(df)
    st.divider()
    _render_deployments_per_week(df)
    st.divider()
    _render_success_rate_trend(df)
    st.divider()
    _render_frequency(df)
    st.divider()
    _render_lead_time(df)
    st.divider()
    _render_avg_duration(history)
    st.divider()
    _render_by_project(df)
    st.divider()
    _render_by_day_of_week(df)
    st.divider()
    _render_recent_table(df)
    st.divider()
    _render_export(df)
