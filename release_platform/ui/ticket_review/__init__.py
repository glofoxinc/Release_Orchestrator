"""Ticket Review Formatter — group tickets by owner, generate formatted list."""

from __future__ import annotations

import streamlit as st

from release_platform.ui.css import render_stepper
from release_platform.ui.helpers import ss_default

APP_META = {
    "id": "ticket_review",
    "label": "Ticket Review",
    "icon": "\U0001f4cb",
        "description": "Lock tickets by fix version or board status, then group for review.",
    "accent": "#8b5cf6",
    "requires_projects": True,
    "requires_service_desk": False,
    "step_labels": ["Select Tickets", "Review Tickets", "Format & Copy"],
}

_LABELS = APP_META["step_labels"]


def render() -> None:
    from release_platform.ui.ticket_review import step1_select, step2_group, step3_format
    from release_platform.ui.workflow import render_app_prerequisite_gate, render_step_banner, render_workflow_status_strip

    if not render_app_prerequisite_gate("ticket_review"):
        return

    render_workflow_status_strip()

    ss_default("tr_step", 1)
    step = st.session_state["tr_step"]
    render_stepper(step, _LABELS)
    render_step_banner("ticket_review", step, total_steps=len(_LABELS))

    if step == 1:
        step1_select.render()
    elif step == 2:
        step2_group.render()
    elif step == 3:
        step3_format.render()
