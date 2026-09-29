"""Integration capability banners — UI matches archived vs active backends."""

from __future__ import annotations

import streamlit as st

import config


def render_archived_integrations_note(*, compact: bool = False) -> None:
    """Show which external integrations are manual-only in this build."""
    archived: list[str] = []
    if config.slack_archived():
        archived.append("Slack announce (archived — manual post)")
    if config.teams_archived():
        archived.append("Teams scheduling (archived — not wired in UI)")
    if config.sharepoint_upload_archived():
        archived.append("SharePoint Graph upload (archived — paste link manually)")
    if not archived:
        return
    text = " · ".join(archived)
    if compact:
        st.caption(f"Integrations: {text}")
    else:
        st.info(
            f"**Integration note:** {text}. "
            "Jira and manual SharePoint link paste remain the active path."
        )
