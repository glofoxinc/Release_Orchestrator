"""Service Ticket Creator — deployment tickets with ADF formatting."""

from __future__ import annotations

import streamlit as st

from release_platform.ui.css import render_stepper
from release_platform.ui.helpers import ss_default

APP_META = {
    "id": "service_ticket",
    "label": "Service Ticket",
    "icon": "\U0001f3ab",
    "description": "Create deployment tickets with ADF formatting, plans, and approvers.",
    "accent": "#f59e0b",
    "requires_projects": True,
    "requires_service_desk": True,
    "step_labels": [
        "Select Tickets",
        "Details",
        "Description",
        "Plans",
        "Preview",
        "Create",
    ],
}

_LABELS = APP_META["step_labels"]


def render() -> None:
    from release_platform.ui.helpers import sync_sharepoint_from_shared
    from release_platform.ui.service_ticket import (
        step1_select,
        step2_details,
        step3_description,
        step4_plans,
        step5_preview,
        step5_review,
    )
    from release_platform.ui.workflow import (
        disable_service_ticket_standalone,
        is_service_ticket_standalone,
        render_app_prerequisite_gate,
        render_step_banner,
        render_workflow_status_strip,
    )

    sync_sharepoint_from_shared()

    if not render_app_prerequisite_gate("service_ticket"):
        return

    from release_platform.ui.integration_status import render_archived_integrations_note

    render_archived_integrations_note(compact=True)

    if is_service_ticket_standalone():
        st.markdown(
            '<div class="jt-banner jt-banner--info" style="margin-bottom:12px">'
            "<strong>Quick start mode</strong> — create SHIPIT directly. Pick tickets by "
            "fix version or Jira status (PIC: Review, AN: Passed QA), paste SharePoint link, "
            "and create the change ticket.</div>",
            unsafe_allow_html=True,
        )
        if st.button("Switch to full workflow", key="stk_exit_standalone"):
            disable_service_ticket_standalone()
            st.rerun()
    else:
        render_workflow_status_strip()

    ss_default("stk_step", 1)
    step = st.session_state["stk_step"]

    # Special views outside the main wizard
    if step == -10:
        from release_platform.ui import tckt_history
        if st.button("Back to Service Ticket", key="stk_back_from_hist"):
            st.session_state["stk_step"] = 1
            st.rerun()
        tckt_history.render_list(embedded=True)
        return

    render_stepper(step, _LABELS)
    render_step_banner("service_ticket", step, total_steps=len(_LABELS))

    if step == 1:
        step1_select.render()
    elif step == 2:
        step2_details.render()
    elif step == 3:
        step3_description.render()
    elif step == 4:
        step4_plans.render()
    elif step == 5:
        step5_preview.render()
    elif step == 6:
        step5_review.render()
