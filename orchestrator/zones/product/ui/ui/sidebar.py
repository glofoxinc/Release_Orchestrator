"""Sidebar rendering -- adapts to home vs. active app."""

from __future__ import annotations

import logging

import streamlit as st

import config
import jira_client
import release_stats
from release_platform.ui.helpers import (
    get_shared_release_summary,
    load_history,
    reset_app,
    reset_wizard,
    user_initials,
)
from release_platform.ui.theme import render_sidebar_brand, render_sidebar_promo

logger = logging.getLogger(__name__)


def _fetch_my_tckts() -> list[dict]:
    """Callable used by release_stats — kept here so it's easy to mock in tests."""
    if not config.TCKT_PROJECT_KEY:
        return []
    try:
        return jira_client.search_my_service_desk_tickets(config.TCKT_PROJECT_KEY)
    except Exception:
        logger.debug("Failed to fetch TCKTs for sidebar stats", exc_info=True)
        return []


def _render_request_type_banner(active_app: str | None) -> None:
    """Warn when Service Desk request-type auto-set is disabled."""
    if not config.SERVICE_DESK_ENABLED:
        return
    if active_app not in (None, "service_ticket", "settings"):
        return
    if config.service_desk_request_type_configured():
        return
    st.warning(
        "Request Type auto-set is not configured — after creating a SHIPIT ticket you must set the "
        "request type manually in the Jira portal until this is fixed. "
        "Go to **Settings → Service Desk → Fetch from Jira**, select your change type, and save.",
        icon=":material/warning:",
    )


def _render_quick_stats() -> None:
    """Defer Jira stats until the operator expands the panel (avoids startup fetch)."""
    st.markdown(
        '<div class="jt-section-label">Quick Stats</div>',
        unsafe_allow_html=True,
    )
    if not st.session_state.get("_sidebar_stats_loaded"):
        if st.button("Load SHIPIT stats", use_container_width=True, key="sb_load_stats"):
            st.session_state["_sidebar_stats_loaded"] = True
            st.rerun()
        st.caption("Stats load on demand — no Jira call until you click above.")
        return

    timings = st.session_state.get("_release_stats_timings", []) or []
    stats = release_stats.get_cached_stats(
        _fetch_my_tckts,
        cache=st.session_state,
        draft_timings=timings,
    )
    lines = [
        f"**Total SHIPIT tickets:** {stats.total}",
        f"**This quarter:** {stats.this_quarter}",
        f"**This month:** {stats.this_month}",
    ]
    if stats.last_release_date:
        lines.append(f"**Last release:** {stats.last_release_date}")
    if stats.most_used_approver:
        lines.append(f"**Top approver:** {stats.most_used_approver}")
    if stats.avg_draft_to_create_minutes is not None:
        lines.append(f"**Avg draft→create:** {stats.avg_draft_to_create_minutes} min")
    st.markdown("<br/>".join(lines), unsafe_allow_html=True)


def _go_home() -> None:
    for k in list(st.session_state.keys()):
        if k.startswith(("wiz_", "dep_", "paste_", "_prev_paste_",
                         "tr_", "_tr_", "rn_", "_rn_", "stk_", "_stk_", "aitc_")):
            del st.session_state[k]
    st.session_state.pop("wiz_undo_data", None)
    st.session_state.pop("undo_confirm", None)
    st.session_state.pop("active_app", None)
    st.rerun()


def _clear_all() -> None:
    for k in list(st.session_state.keys()):
        if k.startswith(("wiz_", "dep_", "paste_", "_prev_paste_",
                         "tr_", "_tr_", "rn_", "_rn_", "stk_", "_stk_", "aitc_",
                         "shared_", "_shared_")):
            del st.session_state[k]
    st.session_state.pop("wiz_undo_data", None)
    st.session_state.pop("undo_confirm", None)
    st.session_state.pop("active_app", None)
    st.rerun()


def _render_checklist() -> None:
    """Release workflow progress — read-only, no widget keys (avoids stale checkbox state)."""
    from release_platform.ui.workflow import get_workflow_progress

    progress = get_workflow_progress()
    steps = [
        (progress.get("releases"), "1. Releases selected"),
        (progress.get("ticket_review"), "2. Ticket review locked"),
        (progress.get("release_notes"), "3. Release notes generated"),
        (progress.get("sharepoint"), "4. SharePoint link saved"),
        (progress.get("service_ticket"), "5. Change ticket (SHIPIT) created"),
        (progress.get("deployer"), "6. Post-deploy comments posted"),
    ]

    lines = []
    for done, label in steps:
        icon = "\u2705" if done else "\u2b1c"
        style = "opacity:1" if done else "opacity:.55"
        lines.append(f'<div style="{style};font-size:.82rem;padding:2px 0">{icon} {label}</div>')

    st.markdown("".join(lines), unsafe_allow_html=True)
    if not any(done for done, _ in steps):
        st.caption(
            "Complete each app in order: Review → Notes (+ SharePoint) → SHIPIT → Deploy."
        )


def render() -> None:
    active_app = st.session_state.get("active_app")

    with st.sidebar:
        render_sidebar_brand(active_app)

        initials = user_initials()
        email_display = config.JIRA_EMAIL
        st.markdown(
            f'<div style="display:flex;align-items:center;margin:8px 0 12px">'
            f'<span class="avatar">{initials}</span>'
            f'<div><div style="font-size:.82rem;font-weight:700">{email_display}</div>'
            f'<div style="font-size:.72rem;opacity:.55">{config.WORKSPACE_NAME}</div></div></div>',
            unsafe_allow_html=True,
        )

        if active_app:
            if st.button("\u2302  Home", use_container_width=True, key="sb_home"):
                _go_home()

        if active_app == "release_deployer":
            if st.button("\U0001f504 Start Over", use_container_width=True, key="sb_reset_deploy"):
                reset_wizard()
            st.divider()

            history_count = len(load_history())
            hist_label = (
                f"\U0001f4cb History ({history_count})"
                if history_count
                else "\U0001f4cb History"
            )
            if st.button(hist_label, use_container_width=True, disabled=history_count == 0, key="sb_hist"):
                st.session_state["wiz_step"] = -1
                st.session_state.pop("view_history_idx", None)
                st.rerun()
            if history_count == 0:
                st.caption("No deployments yet.")

        elif active_app in ("ticket_review", "release_notes", "service_ticket", "ai_ticket_creator"):
            if st.button("\U0001f504 Start Over", use_container_width=True, key="sb_reset_app"):
                reset_app(active_app)
            if active_app == "service_ticket":
                st.caption("Clears this app and returns to Step 1. Release Notes & ticket lock are kept.")

        st.divider()
        st.markdown('<div class="jt-section-label">Navigation</div>', unsafe_allow_html=True)
        if st.button("\u2699\ufe0f  Settings", use_container_width=True, key="sidebar_settings"):
            st.session_state["active_app"] = "settings"
            st.rerun()
        if st.button("\U0001f50d JQL Search", use_container_width=True, key="sidebar_jql_search"):
            st.session_state["active_app"] = "jql_search"
            st.rerun()

        if active_app in ("service_ticket", "release_deployer", "ticket_review", "release_notes"):
            st.divider()
            st.markdown(
                '<div class="jt-section-label">Release Workflow</div>',
                unsafe_allow_html=True,
            )
            _render_checklist()

        shared = get_shared_release_summary()
        if shared:
            st.divider()
            st.markdown(
                f'<div class="jt-banner jt-banner--info" style="font-size:.78rem">'
                f"<strong>Active release</strong><br>{shared}</div>",
                unsafe_allow_html=True,
            )
            if st.button("New Release", use_container_width=True, key="sidebar_new_release"):
                _clear_all()

        _render_request_type_banner(active_app)

        if active_app == "service_ticket":
            st.divider()
            if st.button("SHIPIT History", use_container_width=True, key="sb_tckt_history"):
                st.session_state["stk_step"] = -10
                st.rerun()
            _render_quick_stats()

        st.divider()
        render_sidebar_promo()
        st.caption("\U0001f512 Run only on trusted networks. Credentials are stored in `.env` on this machine.")
