"""Step 5 — Ticket preview (dedicated preview before ticket creation)."""

from __future__ import annotations

import logging
import time

import streamlit as st

import adf_builder as adf
import approver_validator
import config
from consolidation_detector import apply_suggestion, detect_consolidation_opportunities
from ticket_validator import apply_auto_fix, validate_coverage
from release_platform.ui import preview
from release_platform.ui.helpers import invalidate_stk_plans
from release_platform.ui.workflow import render_action_hint

logger = logging.getLogger(__name__)


def _go(step: int) -> None:
    from release_platform.ui.service_ticket.nav import go_step

    go_step(step)


def _render_consolidation_suggestions(extracted: list[dict]) -> None:
    suggestions = detect_consolidation_opportunities(extracted)
    if not suggestions:
        return
    st.markdown("### Consolidation Suggestions")
    st.caption(
        "These tickets share a dashboard or client — merging them produces one "
        "clean bullet per dashboard, matching the TCKT rule."
    )
    for idx, s in enumerate(suggestions):
        with st.container(border=True):
            st.markdown(
                f"**{s.label}** · {len(s.tickets)} tickets ({', '.join(s.tickets)})"
            )
            st.caption(f"Suggestion: consolidate {len(s.tickets)} tickets into one dashboard entry")
            st.code(s.merged_bullet, language="markdown")
            if st.button(
                f"Apply consolidation for {s.label}",
                key=f"stk_merge_{idx}",
                help="Replaces the individual bullets with one merged entry.",
            ):
                new_extracted = apply_suggestion(extracted, s)
                st.session_state["stk_extracted"] = new_extracted
                from release_platform.ui.service_ticket.step3_description import (
                    _build_description_adf,
                    sync_description_adf,
                )

                st.session_state["stk_description_custom"] = False
                st.session_state["stk_description_adf"] = sync_description_adf(
                    new_extracted,
                    st.session_state.get("stk_sharepoint", ""),
                )
                st.session_state["stk_description_text"] = adf.adf_to_plain_text(
                    _build_description_adf(
                        new_extracted,
                        st.session_state.get("stk_sharepoint", ""),
                    )
                )
                invalidate_stk_plans()
                logger.info(
                    "Applied consolidation suggestion for '%s' across %d tickets",
                    s.label, len(s.tickets),
                )
                st.rerun()


def _render_approver_preflight() -> None:
    st.markdown("### Approver Pre-flight")
    defaults = config.TCKT_DEFAULTS
    approvers = defaults.get("approvers", []) or []
    groups = defaults.get("approver_groups", []) or []

    if not approvers and not groups:
        st.info("No default approvers or groups configured — skip pre-flight.")
        return

    if st.button("Validate Approvers", key="stk_preflight_btn"):
        cache = st.session_state.setdefault("_approver_validation_cache", {})
        result = approver_validator.validate_defaults(approvers, groups, cache=cache)
        st.session_state["stk_approver_validation"] = result

    result = st.session_state.get("stk_approver_validation")
    if result is None:
        st.caption(
            f"Pre-flight will validate {len(approvers)} approver(s) and "
            f"{len(groups)} group(s) via the Jira API."
        )
        return

    if result.all_ok:
        st.success("All approvers and groups validated successfully.")
    else:
        st.error("Pre-flight found issues:")
        for msg in result.failures:
            st.markdown(f"- {msg}")
    for a in result.approvers:
        icon = "✅" if a.ok else "⚠️"
        st.markdown(f"{icon} {a.display_name or a.name or a.account_id} — {a.error or 'OK'}")
    for g in result.groups:
        icon = "✅" if g.ok else "⚠️"
        st.markdown(f"{icon} Group '{g.name}' — {g.error or 'OK'}")


def _render_coverage_validation(ticket_data: dict) -> None:
    st.markdown("### Coverage Validation")
    warnings = validate_coverage(ticket_data)
    if not warnings:
        st.success("All dashboards and ticket references are consistent.")
        return
    for idx, w in enumerate(warnings):
        with st.container(border=True):
            st.warning(w.message)
            if w.missing:
                st.caption("Missing items:")
                for m in w.missing:
                    st.markdown(f"- {m}")
            if w.auto_fix:
                if st.button(f"Auto-fix: {w.code}", key=f"stk_autofix_{idx}"):
                    new_data = apply_auto_fix(ticket_data, w)
                    if "test_plan" in new_data:
                        st.session_state["stk_test_plan"] = new_data["test_plan"]
                    if "business_impact" in new_data:
                        st.session_state["stk_business_impact"] = new_data["business_impact"]
                    st.rerun()


def render() -> None:
    ss = st.session_state
    extracted = ss.get("stk_extracted", [])
    if not extracted:
        st.warning("Missing ticket data. Please go through all steps first.")
        if st.button("Back to Start"):
            _go(1)
        return

    # ── Draft timing: capture entry into preview step ───────────
    if "stk_draft_started_at" not in ss:
        ss["stk_draft_started_at"] = time.time()

    # ── Consolidation suggestions first (may mutate extracted) ──
    _render_consolidation_suggestions(extracted)

    # ── Render the preview ──────────────────────────────────────
    payload = preview.build_ticket_payload(ss)
    preview.render_preview(payload)

    # ── Coverage + approver pre-flight ──────────────────────────
    coverage_input = {
        **payload,
        "description": payload.get("description_adf"),
        "extracted": extracted,
    }
    _render_coverage_validation(coverage_input)
    _render_approver_preflight()

    # ── Navigation ──────────────────────────────────────────────
    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Back", key="stk_preview_back"):
            _go(4)
    with c2:
        if st.button("Continue to Create", type="primary", key="stk_preview_next"):
            _go(6)
        render_action_hint(
            "Final review step — confirm everything before the irreversible Jira create."
        )
