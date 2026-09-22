"""Release Notes readiness panel for Streamlit Step 3 / Step 4."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import streamlit as st

from generators.release_notes_insights import (
    ReadinessReport,
    ReleaseInsight,
    assess_release_notes_readiness,
    build_release_summary_paragraph,
    readiness_data_from_session,
)
from release_platform.ui.helpers import build_rn_readiness_payload, esc

_READINESS_CACHE_KEY = "_rn_readiness_cache"


def invalidate_readiness_cache(ss: dict[str, Any] | None = None) -> None:
    """Drop cached readiness report after Step 3 field edits."""
    target = ss if ss is not None else st.session_state
    target.pop(_READINESS_CACHE_KEY, None)


def _readiness_fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assess_readiness_cached(ss: dict[str, Any]) -> ReadinessReport:
    """Run readiness assessment at most once per render cycle for the same inputs."""
    payload = build_rn_readiness_payload(ss)
    fp = _readiness_fingerprint(payload)
    cached = ss.get(_READINESS_CACHE_KEY)
    if isinstance(cached, dict) and cached.get("fp") == fp and cached.get("report") is not None:
        return cached["report"]
    report = assess_release_notes_readiness(payload)
    ss[_READINESS_CACHE_KEY] = {"fp": fp, "report": report}
    return report


def _render_insight_group(title: str, items: list[ReleaseInsight], icon: str) -> None:
    if not items:
        return
    st.markdown(f"**{icon} {title}**")
    for item in items:
        line = esc(item.message)
        if item.action:
            line += f" — _{esc(item.action)}_"
        st.markdown(f"- {line}")


def render_release_notes_readiness(
    ss: dict[str, Any],
    *,
    show_apply_summary: bool = False,
    summary_session_key: str = "rn_summary_p1",
) -> ReadinessReport:
    """Show readiness score, stats, and actionable insights. Returns the report."""
    report = assess_readiness_cached(ss)
    stats = report.stats

    if report.ready and not report.warnings:
        st.success(
            f"**{esc(report.score_label)}** ({report.score}/100) — template sections are aligned for publish."
        )
    elif report.ready:
        st.warning(
            f"**{esc(report.score_label)}** ({report.score}/100) — review warnings below before SharePoint upload."
        )
    else:
        st.error(
            f"**{esc(report.score_label)}** ({report.score}/100) — resolve blockers before generating the final DOCX."
        )

    st.progress(report.score / 100.0, text=f"Readiness score: {report.score}/100")

    metric_cols = st.columns(5)
    metrics = [
        ("Tickets", stats.get("total_tickets", 0)),
        ("Analyze", stats.get("analyze_tickets", 0)),
        ("Custom", stats.get("custom_tickets", 0)),
        ("Dashboards", stats.get("dashboards", 0)),
        ("Paginated", stats.get("paginated", 0)),
    ]
    for col, (label, value) in zip(metric_cols, metrics):
        col.metric(label, value)

    if stats.get("custom_clients"):
        st.caption(f"Custom clients: **{esc(', '.join(stats['custom_clients']))}**")

    ok_items = [item for item in report.insights if item.level == "ok"]
    _render_insight_group("All clear", ok_items, "✅")
    _render_insight_group("Blockers", report.blockers, "⛔")
    _render_insight_group("Warnings", report.warnings, "⚠️")
    _render_insight_group("Suggestions", report.suggestions, "💡")

    extracted = ss.get("rn_extracted") or []
    if show_apply_summary and extracted:
        suggested = build_release_summary_paragraph(extracted)
        if suggested and suggested != (ss.get(summary_session_key) or "").strip():
            if st.button("Apply suggested Release Summary", key="rn_apply_summary"):
                st.session_state[summary_session_key] = suggested
                ss.pop(_READINESS_CACHE_KEY, None)
                st.rerun()

    return report


def render_release_notes_e2e_checklist(ss: dict[str, Any]) -> None:
    """Platform E2E pipeline checklist (generator, publish gate, handoff steps)."""
    from generators.release_notes_e2e import e2e_pipeline_steps
    from generators.release_notes_generator import GENERATOR_BUILD_ID
    from generators.release_notes_insights import assess_release_notes_readiness
    from generators.release_notes_sample import sample_release_notes_data

    data = build_rn_readiness_payload(ss)
    report = assess_readiness_cached(ss)
    fixture_report = assess_release_notes_readiness(sample_release_notes_data())
    publish_ok = report.ready
    steps = e2e_pipeline_steps(readiness=fixture_report)

    # Override session-specific steps
    session_steps = [
        {
            "id": "session_tickets",
            "label": "Tickets selected",
            "ok": bool(data.get("extracted") or data.get("change_rows")),
            "detail": f"{len(data.get('extracted') or [])} ticket(s) in draft",
        },
        {
            "id": "session_readiness",
            "label": "Current draft readiness",
            "ok": report.ready,
            "detail": f"{report.score}/100 — {report.score_label}",
        },
        {
            "id": "session_docx",
            "label": "DOCX generated this session",
            "ok": bool(ss.get("shared_docx_generated") or ss.get("rn_docx_bytes")),
            "detail": ss.get("shared_docx_filename") or ss.get("rn_docx_filename") or "not yet generated",
        },
        {
            "id": "session_sharepoint",
            "label": "SharePoint link for SHIPIT",
            "ok": bool((ss.get("shared_sharepoint_url") or "").strip()),
            "detail": "paste or upload on Step 4" if not ss.get("shared_sharepoint_url") else "link saved",
        },
    ]

    with st.expander(
        f"E2E pipeline — generator `{GENERATOR_BUILD_ID}` · "
        f"{'ready' if publish_ok else 'complete steps below'}",
        expanded=False,
    ):
        st.markdown("**Your release draft**")
        for step in session_steps:
            icon = "✅" if step.get("ok") else "⬜"
            st.markdown(f"{icon} **{esc(step.get('label', ''))}** — {esc(step.get('detail', ''))}")
        st.markdown("**Platform capabilities**")
        for step in steps:
            icon = "✅" if step.get("ok") else "⬜"
            line = f"{icon} **{esc(step.get('label', ''))}** — {esc(step.get('detail', ''))}"
            if not step.get("ok") and step.get("fix"):
                line += f"  \n*Fix:* {esc(step['fix'])}"
            st.markdown(line)
