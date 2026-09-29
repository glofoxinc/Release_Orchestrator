"""Home page -- team selector + app launcher grid."""

from __future__ import annotations

import re

import streamlit as st

import config
from release_platform.ui.app_registry import get_optional_apps, get_primary_apps
from release_platform.ui.health import render_production_readiness_panel, render_setup_health_panel
from release_platform.ui.helpers import esc, get_shared_release_summary, get_snapshot, persist_workspace_to_env
from release_platform.ui.theme import render_top_bar
from release_platform.ui.workflow import (
    WORKFLOW_STEPS,
    PrerequisiteResult,
    batch_app_prerequisites,
    render_workflow_progress_bar,
)

# ── Team selector strip ──────────────────────────────────────────────

def _render_team_strip() -> None:
    """Show all teams/groups as cards at the top. Active team is highlighted."""
    teams = config.list_all_teams()
    active_id = config.active_workspace_name()

    st.markdown(
        '<div class="jt-section-label">Select your team</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(min(len(teams) + 1, 4), gap="small")

    for idx, team in enumerate(teams):
        is_active = team["id"] == active_id
        with cols[idx % (len(teams) + 1)]:
            if is_active:
                badge = '<span class="jt-badge-active">ACTIVE</span>'
                card_cls = "jt-team-card jt-team-card--active"
            else:
                badge = ""
                card_cls = "jt-team-card"

            projs = esc(team["projects"]) if team["projects"] else "No projects"
            st.markdown(
                f'<div class="{card_cls}">'
                f'<div class="jt-team-card__name">{esc(team["name"])}{badge}</div>'
                f'<div class="jt-team-card__meta">{projs}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            if is_active:
                st.button(
                    "\u2713 Active",
                    key=f"team_{idx}",
                    use_container_width=True,
                    disabled=True,
                )
            else:
                if st.button(
                    "Switch",
                    key=f"team_{idx}",
                    use_container_width=True,
                ):
                    from session_persist import persist_session

                    persist_session(dict(st.session_state))
                    config.switch_workspace(team["id"])
                    persist_workspace_to_env(team["id"])
                    for k in list(st.session_state.keys()):
                        if k not in ("active_app",):
                            del st.session_state[k]
                    st.session_state.pop("active_app", None)
                    st.rerun()

    with cols[len(teams) % (len(teams) + 1)]:
        st.markdown(
            '<div style="border:2px dashed rgba(150,150,150,.2);border-radius:14px;'
            "padding:16px 18px;min-height:90px;display:flex;flex-direction:column;"
            'justify-content:center;align-items:center">'
            '<div style="font-size:1.3rem;opacity:.3;margin-bottom:4px">+</div>'
            '<div style="font-size:.82rem;opacity:.4;font-weight:600">New Team</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Create", key="team_add_new", use_container_width=True):
            st.session_state["_home_show_create"] = True
            st.rerun()

    if st.session_state.get("_home_show_create"):
        _render_create_team()


def _render_create_team() -> None:
    """Show inline form to create a new team workspace."""
    st.markdown("")
    st.markdown(
        '<div style="border:1px solid rgba(59,130,246,.25);border-radius:14px;'
        "padding:20px 24px;background:rgba(59,130,246,.04);"
        'margin-bottom:16px">'
        '<div style="font-size:1rem;font-weight:700;margin-bottom:12px">'
        'Create New Team Workspace</div></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        team_name = st.text_input(
            "Team / Group Name",
            placeholder="e.g. Analytics Team",
            key="_new_team_name",
            help="Display name shown in the UI and sidebar.",
        )
    with c2:
        folder_hint = re.sub(r"[^a-zA-Z0-9\-]", "-", team_name.lower().strip()) if team_name else ""
        folder_name = st.text_input(
            "Folder Name",
            value=folder_hint,
            placeholder="analytics-team",
            key="_new_team_folder",
            help="Folder name under workspaces/ — lowercase, hyphens only.",
        )

    c1, c2, c3 = st.columns([2, 2, 4])
    with c1:
        if st.button("Create & Configure", type="primary", key="_new_team_go", use_container_width=True):
            if team_name.strip() and folder_name.strip():
                clean_folder = re.sub(r"[^a-zA-Z0-9\-]", "-", folder_name.strip().lower())
                config.create_workspace(clean_folder, team_name.strip())
                config.switch_workspace(clean_folder)
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.session_state["active_app"] = "settings"
                st.rerun()
            else:
                st.error("Both fields are required.")
    with c2:
        if st.button("Cancel", key="_new_team_cancel", use_container_width=True):
            st.session_state.pop("_home_show_create", None)
            st.rerun()


# ── App launcher cards ───────────────────────────────────────────────

def _render_app_card(
    app: dict,
    *,
    prereq: "PrerequisiteResult | None" = None,
) -> None:
    accent = app["accent"]
    locked = prereq is not None and not prereq.ok
    lock_hint = ""
    if locked and prereq and prereq.missing:
        lock_hint = (
            f'<div class="jt-app-card__meta jt-diff-changed" style="margin-top:6px">'
            f"Needs: {esc(prereq.missing[0])}</div>"
        )
    if app["id"] == "service_ticket" and locked:
        lock_hint += (
            '<div class="jt-app-card__meta" style="margin-top:4px">'
            "Or use <strong>Quick start</strong> below — no prior steps required.</div>"
        )
    if app["id"] == "release_deployer" and locked:
        lock_hint += (
            '<div class="jt-app-card__meta" style="margin-top:4px">'
            "Or use <strong>Quick start</strong> below — skip straight to post-deploy.</div>"
        )
    if app["id"] == "release_notes" and locked:
        lock_hint += (
            '<div class="jt-app-card__meta" style="margin-top:4px">'
            "Or use <strong>Quick start</strong> below — pick tickets without Ticket Review lock.</div>"
        )

    st.markdown(
        f'<div class="jt-app-card" style="--card-accent:{accent}">'
        f'<div class="jt-app-card__icon">{app["icon"]}</div>'
        f'<div class="jt-app-card__title">{esc(app["title"])}</div>'
        f'<div class="jt-app-card__subtitle">{esc(app.get("subtitle", ""))}</div>'
        f'<div class="jt-app-card__desc">{esc(app["description"])}</div>'
        f'<div class="jt-app-card__meta">{esc(app.get("meta", ""))}</div>'
        f"{lock_hint}"
        f"</div>",
        unsafe_allow_html=True,
    )
    if app["id"] == "service_ticket" and locked:
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Quick start \u2192",
                key=f"open_{app['id']}_standalone",
                type="primary",
                use_container_width=True,
            ):
                from release_platform.ui.workflow import enable_service_ticket_standalone

                enable_service_ticket_standalone()
                st.session_state["active_app"] = app["id"]
                st.rerun()
        with c2:
            if st.button(
                "View requirements \u2192",
                key=f"open_{app['id']}_main",
                use_container_width=True,
            ):
                st.session_state["active_app"] = app["id"]
                st.rerun()
        return

    if app["id"] == "release_deployer" and locked:
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Quick start \u2192",
                key=f"open_{app['id']}_standalone",
                type="primary",
                use_container_width=True,
            ):
                from release_platform.ui.workflow import enable_deployer_standalone

                enable_deployer_standalone()
                st.session_state["active_app"] = app["id"]
                st.rerun()
        with c2:
            if st.button(
                "View requirements \u2192",
                key=f"open_{app['id']}_main",
                use_container_width=True,
            ):
                st.session_state["active_app"] = app["id"]
                st.rerun()
        return

    if app["id"] == "release_notes" and locked:
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Quick start \u2192",
                key=f"open_{app['id']}_standalone",
                type="primary",
                use_container_width=True,
            ):
                from release_platform.ui.workflow import enable_release_notes_standalone

                enable_release_notes_standalone()
                st.session_state["active_app"] = app["id"]
                st.rerun()
        with c2:
            if st.button(
                "View requirements \u2192",
                key=f"open_{app['id']}_main",
                use_container_width=True,
            ):
                st.session_state["active_app"] = app["id"]
                st.rerun()
        return

    btn_label = "View requirements \u2192" if locked else "Open \u2192"
    if st.button(
        btn_label,
        key=f"open_{app['id']}_{'opt' if app.get('optional') else 'main'}",
        type="primary",
        use_container_width=True,
    ):
        st.session_state["active_app"] = app["id"]
        st.rerun()


def _render_app_grid(apps: list[dict]) -> None:
    if not apps:
        return
    workflow_ids = {ws.id for ws in WORKFLOW_STEPS}
    ids = tuple(app["id"] for app in apps if app["id"] in workflow_ids)
    prereqs = batch_app_prerequisites(ids)
    cols = st.columns(2, gap="medium")
    for i, app in enumerate(apps):
        with cols[i % 2]:
            _render_app_card(
                app,
                prereq=prereqs.get(app["id"]) if app["id"] in workflow_ids else None,
            )


def _render_getting_started() -> None:
    """Single help section — operator-facing only."""
    with st.expander("Getting started", expanded=False):
        st.markdown(
            "1. **Select your team** above.\n"
            "2. **Ticket Review** — lock the release ticket list.\n"
            "3. **Release Notes** — generate the Word file, upload to SharePoint, paste the link.\n"
            "4. **Service Ticket** — create the SHIPIT change ticket.\n"
            "5. **Release Deployer** — post deployment comments and mark tickets Done.\n\n"
            "Each app has **Quick start** if you want to skip an earlier step."
        )


# ── Main render ──────────────────────────────────────────────────────

def render() -> None:
    render_top_bar(
        breadcrumb="Orchestrator / Dashboard",
        title="Release Orchestrator",
        subtitle=f"{esc(config.WORKSPACE_NAME)} · Ticket Review → Release Notes → SHIPIT → Deployer",
    )

    render_setup_health_panel(operator_mode=True)
    render_production_readiness_panel()

    _render_team_strip()

    st.markdown("")
    st.markdown('<div class="jt-section-label">Release workflow progress</div>', unsafe_allow_html=True)
    render_workflow_progress_bar()
    st.caption(
        "Steps 1–4: Ticket Review → Release Notes (.docx) → SHIPIT → Deployer. "
        "Paste the SharePoint link on Release Notes Step 4 before creating SHIPIT."
    )

    st.markdown("")

    # Active release banner
    shared_summary = get_shared_release_summary()
    snap = get_snapshot()
    if shared_summary:
        if snap:
            count = len(snap.get("ticket_keys", []))
            locked_at = snap.get("locked_at", "?")
            detail = (
                f"<strong>{esc(config.WORKSPACE_NAME)} \u2022 Active release:</strong> "
                f"{esc(shared_summary)} "
                f"&mdash; locked at {esc(locked_at)}, {count} tickets"
            )
            banner_cls = "jt-banner jt-banner--success"
        else:
            detail = (
                f"<strong>{esc(config.WORKSPACE_NAME)} \u2022 Active release:</strong> "
                f"{esc(shared_summary)} "
                f"&mdash; selections carry across all apps"
            )
            banner_cls = "jt-banner jt-banner--info"
        st.markdown(
            f'<div class="{banner_cls}">{detail}</div>',
            unsafe_allow_html=True,
        )

    # App grid — core workflow only; optional tools live in collapsed section below
    primary_apps = get_primary_apps()
    optional_apps = get_optional_apps()
    if not primary_apps and not optional_apps:
        st.info(
            f"**{esc(config.WORKSPACE_NAME)}** has no apps enabled yet. "
            "Go to **Settings** to add projects and enable apps."
        )
        if st.button("\u2699\ufe0f Open Settings", type="primary"):
            st.session_state["active_app"] = "settings"
            st.rerun()
        return

    st.markdown('<div class="jt-section-label">Workflow apps</div>', unsafe_allow_html=True)
    _render_app_grid(primary_apps)

    if optional_apps:
        with st.expander("Optional features", expanded=False):
            st.caption("Extra tools outside the core release workflow.")
            _render_app_grid(optional_apps)

    _render_getting_started()
