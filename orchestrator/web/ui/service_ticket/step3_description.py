"""Step 3 — Auto-build, preview, and optionally edit the TCKT description."""

from __future__ import annotations

import streamlit as st

import adf_builder as adf
import config
import schedule_time
from generators.shipit_evidence_plans import build_evidence_description_adf
from generators.shipit_ticket_evidence import enrich_extracted_with_jira_evidence
from release_platform.ui import preview
from release_platform.ui.helpers import release_notes_doc_filename, ss_default, sync_sharepoint_from_shared
from release_platform.ui.workflow import render_action_hint


def _go(step: int) -> None:
    from release_platform.ui.service_ticket.nav import go_step

    go_step(step)


def _window_statement() -> dict[str, str]:
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


def _version_label() -> str:
    for proj in config.PROJECTS:
        rel = st.session_state.get(f"stk_release_{proj['key']}")
        if rel and rel.get("name"):
            return rel["name"]
    return ""


def _build_description_adf(extracted: list[dict], sharepoint_url: str) -> dict:
    """Build SHIPIT evidence-based ADF description (17036 / 17191 gold standards)."""
    version = _version_label()
    version_label = f"v{version}" if version and not str(version).lower().startswith("v") else version
    link_label = release_notes_doc_filename("stk_") if sharepoint_url else None
    enriched = enrich_extracted_with_jira_evidence(extracted)
    return build_evidence_description_adf(
        enriched,
        version_label=version_label,
        window=_window_statement(),
        sharepoint_url=sharepoint_url,
        sharepoint_label=link_label,
    )


def sync_description_adf(extracted: list[dict], sharepoint: str) -> dict:
    """Return auto-built or user-customized description ADF."""
    ss = st.session_state
    if ss.get("stk_description_custom") and ss.get("stk_description_text", "").strip():
        return adf.plain_text_to_doc(ss["stk_description_text"])
    return _build_description_adf(extracted, sharepoint)


def render() -> None:
    sync_sharepoint_from_shared()
    st.markdown("## Description")
    st.markdown(
        "The description is auto-built from your tickets. You can preview it, "
        "edit the text directly, or reset back to the auto-generated version."
    )

    extracted = st.session_state.get("stk_extracted", [])
    sharepoint = (
        st.session_state.get("stk_sharepoint", "")
        or st.session_state.get("shared_sharepoint_url", "")
    ).strip()

    if not extracted:
        st.warning("No ticket data found. Please select releases first.")
        if st.button("\u2190 Back to Release Selection"):
            _go(1)
        return

    auto_adf = _build_description_adf(extracted, sharepoint)
    ss_default("stk_description_custom", False)
    ss_default("stk_description_text", adf.adf_to_plain_text(auto_adf))

    custom = st.checkbox(
        "Customize description (edit text below)",
        value=st.session_state.get("stk_description_custom", False),
        key="_stk_desc_custom",
        help="When checked, your edited text is used instead of the auto-generated description.",
    )
    st.session_state["stk_description_custom"] = custom

    if custom:
        st.session_state["stk_description_text"] = st.text_area(
            "Description text",
            value=st.session_state.get("stk_description_text", ""),
            height=320,
            key="_stk_desc_text",
            help="Use blank lines for paragraphs. Lines starting with '- ' become bullet items.",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Reset to auto-generated", key="stk_desc_reset"):
                st.session_state.pop("_stk_desc_custom", None)
                st.session_state.pop("_stk_desc_text", None)
                st.session_state["stk_description_custom"] = False
                st.session_state["stk_description_text"] = adf.adf_to_plain_text(auto_adf)
                st.rerun()
        with c2:
            if sharepoint and st.button("Insert SharePoint link", key="stk_desc_add_sp"):
                link_label = release_notes_doc_filename("stk_")
                current = st.session_state.get("stk_description_text", "").rstrip()
                st.session_state.pop("_stk_desc_text", None)
                st.session_state["stk_description_text"] = f"{current}\n\n{link_label}"
                st.rerun()
    else:
        st.session_state["stk_description_text"] = adf.adf_to_plain_text(auto_adf)

    desc_adf = sync_description_adf(extracted, sharepoint)
    st.session_state["stk_description_adf"] = desc_adf

    st.markdown("### Preview (as it will appear in Jira)")
    st.markdown(preview.adf_to_html(desc_adf), unsafe_allow_html=True)

    has_analyze = any(e["type"] == "Analyze" for e in extracted)
    has_custom = any(e["type"] == "Custom" for e in extracted)
    custom_clients = sorted({
        e["client"] for e in extracted
        if e["type"] == "Custom" and e["client"] != "Unknown"
    })

    with st.expander("Section checklist", expanded=False):
        scope = []
        if has_analyze:
            scope.append("Standard (Analyze)")
        if has_custom:
            scope.append("Custom")
        st.markdown(f"- **Scope:** {' and '.join(scope)}")
        if has_analyze:
            st.markdown("- **Analyze Clients:** All Analyze-based (Standard) clients")
        if custom_clients:
            st.markdown(f"- **Custom Clients:** {', '.join(custom_clients)}")
        st.markdown(f"- **Report inventory:** {len(extracted)} ticket entries")
        if sharepoint:
            st.markdown("- **SharePoint link:** included")
        else:
            st.warning("No SharePoint link — add one in Step 2.")

    with st.expander("Raw ADF JSON (for debugging)", expanded=False):
        st.json(desc_adf)

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Back", key="stk_s3_back"):
            _go(2)
    with c2:
        if st.button("Edit Plans \u2192", type="primary", key="stk_s3_next"):
            _go(4)
        render_action_hint(
            "Next: edit implementation, test, backout, and business impact plans."
        )
