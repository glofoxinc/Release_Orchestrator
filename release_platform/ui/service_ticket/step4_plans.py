"""Step 4 — Edit Implementation, Test, Backout, and Business Impact plans.

Plans are dynamically generated from templates + ticket data.
"""

from __future__ import annotations

import streamlit as st

import config
import schedule_time
import template_library
from generators.shipit_ticket_evidence import enrich_extracted_with_jira_evidence
from service_ticket_plans import (
    build_backout,
    build_communication,
    build_impact,
    build_impl,
    build_qa_test_plan,
    build_reason,
    build_risks,
    build_test,
    consolidate_by_report,
)
from release_platform.ui.helpers import derive_release_doc_metadata, esc, ss_default, sync_stk_plans_fingerprint
from release_platform.ui.workflow import render_action_hint

# Aliases preserve historical private names used by tests and callers.
_consolidate_by_report = consolidate_by_report
_build_impl = build_impl
_build_test = build_test
_build_backout = build_backout
_build_impact = build_impact
_build_communication = build_communication
_build_reason = build_reason


def _go(step: int) -> None:
    from release_platform.ui.service_ticket.nav import go_step

    go_step(step)


def _render_template_selector() -> None:
    """Render template dropdown for quick preset application."""
    templates = template_library.list_templates()
    if not templates:
        return

    with st.expander("Apply Template (optional)", expanded=False):
        st.caption(
            "Templates provide preset values for classification, risk, and approver groups. "
            "Applying a template fills empty fields without overwriting your edits."
        )

        template_names = ["(none)"] + [t.name for t in templates]
        selected = st.selectbox(
            "Select template",
            options=template_names,
            key="stk_template_select",
            help="Choose a template to apply preset values.",
        )

        if selected and selected != "(none)":
            selected_tpl = next((t for t in templates if t.name == selected), None)
            if selected_tpl:
                st.markdown(f"**Description:** {esc(selected_tpl.description or 'No description')}")
                if selected_tpl.tags:
                    st.markdown(f"**Tags:** {', '.join(esc(t) for t in selected_tpl.tags)}")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Apply template", key="stk_apply_template"):
                        ss = st.session_state
                        current_draft = {
                            "priority": ss.get("stk_priority"),
                            "change_type": ss.get("stk_change_type"),
                            "change_risk": ss.get("stk_change_risk"),
                            "impact": ss.get("stk_impact"),
                            "urgency": ss.get("stk_urgency"),
                            "approver_groups": ss.get("stk_approver_groups"),
                            "implementation_plan": ss.get("stk_impl_plan"),
                            "test_plan": ss.get("stk_test_plan"),
                            "backout_plan": ss.get("stk_backout_plan"),
                            "business_impact": ss.get("stk_business_impact"),
                        }
                        merged = template_library.apply_template(current_draft, selected_tpl)
                        for k, v in merged.items():
                            stk_key = f"stk_{k}" if not k.startswith("stk_") else k
                            ss[stk_key] = v
                        ss["stk_template_applied"] = selected_tpl.name
                        st.rerun()
                with c2:
                    overwrite = st.checkbox("Overwrite existing values", key="stk_template_overwrite")
                    if overwrite:
                        st.warning("This will replace your current values.")

        if st.session_state.get("stk_template_applied"):
            st.success(f"Template '{st.session_state['stk_template_applied']}' applied.")

        st.markdown("---")
        st.markdown("**Save current plans as template** (MCP `save_tckt_template` parity)")
        save_name = st.text_input(
            "Template name",
            placeholder="e.g. glofox-standard-weekly",
            key="stk_save_template_name",
        )
        save_desc = st.text_input(
            "Description (optional)",
            key="stk_save_template_desc",
        )
        if st.button("Save as template", key="stk_save_template_btn"):
            name = (save_name or "").strip()
            if not name:
                st.error("Enter a template name.")
            else:
                ss = st.session_state
                draft = {
                    "priority": ss.get("stk_priority"),
                    "change_type": ss.get("stk_change_type"),
                    "change_risk": ss.get("stk_change_risk"),
                    "impact": ss.get("stk_impact"),
                    "urgency": ss.get("stk_urgency"),
                    "approver_groups": ss.get("stk_approver_groups"),
                    "implementation_plan": ss.get("stk_impl_plan"),
                    "test_plan": ss.get("stk_test_plan"),
                    "backout_plan": ss.get("stk_backout_plan"),
                    "business_impact": ss.get("stk_business_impact"),
                }
                try:
                    captured = template_library.capture_from_draft(
                        name, draft, description=save_desc.strip()
                    )
                    path = template_library.save_template(captured)
                    st.success(f"Saved template **{esc(name)}** → `{path}`")
                except (ValueError, FileExistsError) as exc:
                    st.error(str(exc))


def current_window_statement() -> dict[str, str]:
    """Dual-timezone deployment window wording for the current draft."""
    ss = st.session_state
    start_d = ss.get("stk_planned_start_date")
    start_t = ss.get("stk_planned_start_time")
    end_d = ss.get("stk_planned_end_date")
    end_t = ss.get("stk_planned_end_time")
    if not (start_d and start_t and end_d and end_t):
        return {}
    return schedule_time.window_statement(
        start_d, start_t, end_d, end_t,
        tz_name=ss.get("stk_schedule_tz") or config.TCKT_SCHEDULE_TZ,
        display_tz=config.TCKT_DISPLAY_TZ,
    )


def _get_context() -> dict:
    """Gather all data needed by plan builders."""
    extracted = enrich_extracted_with_jira_evidence(
        list(st.session_state.get("stk_extracted", [])),
    )
    sharepoint = st.session_state.get("stk_sharepoint", "")

    parts = []
    for proj in config.PROJECTS:
        rel = st.session_state.get(f"stk_release_{proj['key']}", {})
        if rel:
            parts.append(rel.get("name", ""))
    version_label, _ = derive_release_doc_metadata("stk_")
    version_name = version_label or " + ".join(dict.fromkeys(p for p in parts if p))

    has_analyze = any(e["type"] == "Analyze" for e in extracted)
    has_custom = any(e["type"] == "Custom" for e in extracted)
    scope = []
    if has_analyze:
        scope.append("Standard (Analyze)")
    if has_custom:
        scope.append("Custom")
    scope_str = " and ".join(scope) or "the project"

    clients = sorted({
        e["client"] for e in extracted
        if e["client"] not in ("Standard", "Unknown")
    })
    dashboards = sorted({e["report"] for e in extracted if e["report"]})
    descriptions = [e for e in extracted if e["description"]]

    workspace_list = ["Standard"]
    workspace_list.extend(clients)
    workspaces = " / ".join(workspace_list)

    return {
        "extracted": extracted,
        "sharepoint": sharepoint,
        "window": current_window_statement(),
        "version": version_name,
        "version_name": version_name,
        "scope_str": scope_str,
        "clients": clients,
        "dashboards": dashboards,
        "descriptions": descriptions,
        "workspaces": workspaces,
        "has_analyze": has_analyze,
        "has_custom": has_custom,
    }


def render() -> None:
    st.markdown("## Deployment Plans")
    st.markdown(
        "Plans are generated from templates + your tickets. "
        "Edit as needed before creating."
    )

    extracted = st.session_state.get("stk_extracted", [])
    if not extracted:
        st.warning("No ticket data found. Go back to **Step 1** and load tickets first.")
        if st.button("\u2190 Back to ticket selection", key="stk_s4_empty_back"):
            _go(1)
        return

    # ── Template selection ───────────────────────────────────────
    _render_template_selector()

    ctx = _get_context()
    sync_stk_plans_fingerprint()

    ss_default("stk_impl_plan", _build_impl(ctx))
    ss_default("stk_test_plan", _build_test(ctx))
    ss_default("stk_backout_plan", _build_backout(ctx))
    ss_default("stk_business_impact", _build_impact(ctx))
    ss_default("stk_communication_plan", _build_communication(ctx))
    ss_default("stk_reason_for_change", _build_reason(ctx))
    ss_default("stk_risks_management", build_risks(ctx))
    ss_default("stk_qa_test_plan", build_qa_test_plan(ctx))

    with st.expander("Implementation Steps", expanded=True):
        st.session_state["stk_impl_plan"] = st.text_area(
            "Implementation Steps",
            value=st.session_state["stk_impl_plan"],
            height=220,
            key="_stk_impl",
            help="Steps to deploy: backup, deploy, validate, notify. Auto-generated from tickets.",
            label_visibility="collapsed",
        )

    with st.expander("Verification Steps", expanded=False):
        st.session_state["stk_test_plan"] = st.text_area(
            "Verification Steps",
            value=st.session_state["stk_test_plan"],
            height=300,
            key="_stk_test",
            help="Validation steps grouped by category. Consolidates by dashboard/report.",
            label_visibility="collapsed",
        )

    with st.expander("Rollback Steps", expanded=False):
        st.session_state["stk_backout_plan"] = st.text_area(
            "Rollback Steps",
            value=st.session_state["stk_backout_plan"],
            height=160,
            key="_stk_back",
            help="Rollback procedure: restore from backup, revert changes, notify.",
            label_visibility="collapsed",
        )

    with st.expander("Business Impact", expanded=False):
        st.session_state["stk_business_impact"] = st.text_area(
            "Business Impact",
            value=st.session_state["stk_business_impact"],
            height=250,
            key="_stk_biz",
            help="Describes what this release improves, per dashboard. Includes SharePoint link.",
            label_visibility="collapsed",
        )

    with st.expander("Communication Plan", expanded=False):
        st.session_state["stk_communication_plan"] = st.text_area(
            "Communication Plan",
            value=st.session_state["stk_communication_plan"],
            height=180,
            key="_stk_comm",
            help="Stakeholder communication steps for the deployment window.",
            label_visibility="collapsed",
        )

    with st.expander("Reason for the Change", expanded=False):
        st.session_state["stk_reason_for_change"] = st.text_area(
            "Reason for the Change",
            value=st.session_state["stk_reason_for_change"],
            height=100,
            key="_stk_reason",
            help="Short summary of why this release is needed.",
            label_visibility="collapsed",
        )

    with st.expander("Risks Management", expanded=False):
        st.session_state["stk_risks_management"] = st.text_area(
            "Risks Management",
            value=st.session_state.get("stk_risks_management", ""),
            height=220,
            key="_stk_risks",
            help="Evidence-based risks — Overall, per-ticket, shared controls (SHIPIT gold standard).",
            label_visibility="collapsed",
        )

    with st.expander("QA Test Plan", expanded=False):
        st.session_state["stk_qa_test_plan"] = st.text_area(
            "QA Test Plan",
            value=st.session_state.get("stk_qa_test_plan", ""),
            height=120,
            key="_stk_qa",
            help="QA validator dates and performance-testing note from release tickets.",
            label_visibility="collapsed",
        )

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Back", key="stk_s4_back"):
            _go(3)
    with c2:
        if st.button("Review & Create \u2192", type="primary", key="stk_s4_next"):
            _go(5)
        render_action_hint(
            "Runs coverage validation and approver checks before the final create step."
        )
