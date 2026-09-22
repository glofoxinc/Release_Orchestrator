"""Design system — theme tokens, top bar, and light/dark/auto switching."""

from __future__ import annotations

import streamlit as st

import config
from release_platform.ui.helpers import UI_BUILD_ID, esc

THEME_KEY = "ui_theme"
VALID_THEMES = ("light", "dark", "auto")


def _theme_mode() -> str:
    mode = st.session_state.get(THEME_KEY, "auto")
    return mode if mode in VALID_THEMES else "auto"


def inject_theme_bootstrap() -> None:
    """Apply saved theme before first paint (runs once per session)."""
    if st.session_state.get("_theme_bootstrapped"):
        return
    st.session_state["_theme_bootstrapped"] = True
    mode = _theme_mode()
    st.iframe(
        f"""
        <script>
        (function() {{
            const KEY = "jira_toolkit_theme";
            const mode = {mode!r} || localStorage.getItem(KEY) || "auto";
            localStorage.setItem(KEY, mode);
            const root = window.parent.document.documentElement;
            const effective = mode === "auto"
                ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
                : mode;
            root.setAttribute("data-theme", effective);
            root.setAttribute("data-theme-mode", mode);
            window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {{
                const m = localStorage.getItem(KEY) || "auto";
                if (m !== "auto") return;
                root.setAttribute("data-theme",
                    window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
            }});
        }})();
        </script>
        """,
        # st.iframe requires a positive size; 1x1 is the smallest invisible footprint
        # for this script-only frame.
        height=1,
        width=1,
    )


def _sync_theme(mode: str) -> None:
    st.iframe(
        f"""
        <script>
        (function() {{
            const KEY = "jira_toolkit_theme";
            const mode = {mode!r};
            localStorage.setItem(KEY, mode);
            const root = window.parent.document.documentElement;
            const effective = mode === "auto"
                ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
                : mode;
            root.setAttribute("data-theme", effective);
            root.setAttribute("data-theme-mode", mode);
        }})();
        </script>
        """,
        height=1,
        width=1,
    )


def render_theme_toggle() -> None:
    """Light / Dark / Auto pill toggle."""
    if THEME_KEY not in st.session_state:
        st.session_state[THEME_KEY] = "auto"

    current = _theme_mode()
    labels = {"light": "Light", "dark": "Dark", "auto": "Auto"}
    cols = st.columns(3, gap="small")
    for idx, mode in enumerate(VALID_THEMES):
        with cols[idx]:
            active = current == mode
            if st.button(
                labels[mode],
                key=f"theme_{mode}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state[THEME_KEY] = mode
                _sync_theme(mode)
                st.rerun()


def render_api_status() -> None:
    """Connected indicator when Jira credentials are present."""
    connected = bool(config.JIRA_EMAIL and config.JIRA_API_TOKEN)
    cls = "jt-status jt-status--ok" if connected else "jt-status jt-status--warn"
    label = "Jira Connected" if connected else "Not Connected"
    st.markdown(
        f'<div class="{cls}"><span class="jt-status__dot"></span>{label}</div>',
        unsafe_allow_html=True,
    )


def render_top_bar(*, breadcrumb: str, title: str, subtitle: str = "") -> None:
    """Page header with breadcrumb, title, theme toggle, and status."""
    sub_html = f'<p class="jt-page-sub">{esc(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f'<div class="jt-topbar">'
        f'<div class="jt-topbar__left">'
        f'<div class="jt-breadcrumb">{esc(breadcrumb)}</div>'
        f'<h1 class="jt-page-title">{esc(title)}</h1>'
        f"{sub_html}"
        f"</div></div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([2.2, 1.2, 1])
    with c2:
        st.markdown('<div class="jt-topbar__label">Theme</div>', unsafe_allow_html=True)
        render_theme_toggle()
    with c3:
        st.markdown('<div class="jt-topbar__label">Status</div>', unsafe_allow_html=True)
        render_api_status()
    st.markdown('<div class="jt-topbar-spacer"></div>', unsafe_allow_html=True)


def render_sidebar_brand(active_app: str | None) -> None:
    """Brand block at top of sidebar."""
    app_labels = {
        "ticket_review": "Ticket Review",
        "release_notes": "Release Notes",
        "service_ticket": "Service Ticket",
        "release_deployer": "Release Deployer",
        "ai_ticket_creator": "AI Ticket Creator",
        "settings": "Settings",
    }
    context = app_labels.get(active_app or "", "Dashboard")
    st.markdown(
        '<div class="jt-brand">'
        '<div class="jt-brand__mark">RO</div>'
        '<div class="jt-brand__text">'
        '<div class="jt-brand__title">Release Orchestrator</div>'
        '<div class="jt-brand__sub">Release Automation Platform</div>'
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="jt-sidebar-context">{esc(context)}</div>',
        unsafe_allow_html=True,
    )


def render_app_header(active_app: str | None) -> None:
    """Top bar for in-app views."""
    if not active_app:
        return
    meta = {
        "settings": ("Orchestrator / Admin", "Settings", "Workspace, projects, and integrations"),
        "release_deployer": ("Orchestrator / Workflow", "Release Deployer", "Post-deploy comments and transitions"),
        "ticket_review": ("Orchestrator / Workflow", "Ticket Review", "Group release tickets by owner"),
        "release_notes": ("Orchestrator / Workflow", "Release Notes", "Generate Word release documents"),
        "service_ticket": ("Orchestrator / Workflow", "Service Ticket", "Create SHIPIT deployment tickets"),
        "ai_ticket_creator": ("Orchestrator / Optional", "AI Ticket Creator", "Natural language to Jira tickets"),
    }
    if active_app not in meta:
        return
    crumb, title, sub = meta[active_app]
    render_top_bar(breadcrumb=crumb, title=title, subtitle=sub)


def render_sidebar_promo() -> None:
    """Gradient feature highlight card."""
    st.markdown(
        '<div class="jt-promo">'
        '<div class="jt-promo__title">Release Workflow Engine</div>'
        '<div class="jt-promo__body">Cross-app release selection, ticket lock-in, '
        "TCKT automation, and Word release notes — one workspace.</div>"
        f'<div class="jt-promo__meta">Build {esc(UI_BUILD_ID)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
