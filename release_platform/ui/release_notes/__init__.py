"""Release Notes Generator — build Word documents from Jira releases."""

from __future__ import annotations

import streamlit as st

from release_platform.ui.css import render_stepper
from release_platform.ui.helpers import ensure_ui_build_sync, ss_default

APP_META = {
    "id": "release_notes",
    "label": "Release Notes",
    "icon": "\U0001f4dd",
    "description": "Auto-generate pixel-perfect Word release notes from Jira tickets.",
    "accent": "#10b981",
    "requires_projects": True,
    "requires_service_desk": False,
    "step_labels": ["Select Tickets", "Tickets", "Edit Content", "Generate"],
}

_LABELS = APP_META["step_labels"]


def render() -> None:
    from release_platform.ui.release_notes import step1_select, step2_tickets, step3_edit, step4_generate
    from release_platform.ui.workflow import (
        disable_release_notes_standalone,
        is_release_notes_standalone,
        render_app_prerequisite_gate,
        render_step_banner,
        render_workflow_status_strip,
    )

    if ensure_ui_build_sync():
        st.info(
            "Release Notes metadata logic was updated. Version and date will now follow "
            "your selected Jira fix version (e.g. `2026.3.07.08` → `v2026.3.07.08`, `08-July-2026`).",
            icon=":material/info:",
        )

    if is_release_notes_standalone():
        st.info(
            "**Quick start mode** — pick tickets by fix version or Jira status, "
            "optional Team filter (PIC / AN). Ticket Review lock is not required."
        )
        if st.button("Switch to full workflow", key="rn_exit_standalone"):
            disable_release_notes_standalone()
            st.rerun()

    if not render_app_prerequisite_gate("release_notes"):
        return

    from release_platform.ui.integration_status import render_archived_integrations_note

    render_archived_integrations_note(compact=True)
    if not is_release_notes_standalone():
        render_workflow_status_strip()

    ss_default("rn_step", 1)
    step = st.session_state["rn_step"]
    render_stepper(step, _LABELS)
    render_step_banner("release_notes", step, total_steps=len(_LABELS))

    if step == 1:
        step1_select.render()
    elif step == 2:
        step2_tickets.render()
    elif step == 3:
        step3_edit.render()
    elif step == 4:
        step4_generate.render()
