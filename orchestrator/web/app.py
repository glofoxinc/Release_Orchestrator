"""Release Orchestrator — Personal Automation Hub."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_FILE = os.path.join(_REPO_ROOT, ".env")
if os.path.isfile(_ENV_FILE):
    load_dotenv(_ENV_FILE, override=True)
os.environ["_JRT_ENV_BOOTSTRAPPED"] = "1"

import streamlit as st

import config
import deploy_draft
from common.logger import set_log_context, setup_logging
from release_platform.ui import home, sidebar
from release_platform.ui.css import inject_design_system, render_stepper
from release_platform.ui.helpers import (
    ENV_FILE,
    ensure_deployer_wizard_version,
    ensure_ui_build_sync,
    save_and_reload_env,
    ss_default,
)
from release_platform.ui.theme import inject_theme_bootstrap, render_app_header

# Structured logging with secret redaction (honours LOG_FORMAT / LOG_LEVEL).
setup_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Release Orchestrator", page_icon="\U0001f9f0", layout="wide")


def _mock_mode_enabled() -> bool:
    """Return True when MOCK_MODE env var is set to a truthy value."""
    return os.environ.get("MOCK_MODE", "").lower() in {"1", "true", "yes", "on"}


# ── Bootstrap workspace (env loaded once above) ─────────────────────
config.ensure_workspace_loaded()
set_log_context(workspace=config.active_workspace_name() or "root")

# Restore full release session after Streamlit restart (workspace-scoped).
if not st.session_state.get("_release_session_prompt_done"):
    try:
        from session_restore import render_startup_restore_prompt

        if render_startup_restore_prompt():
            st.stop()
    except Exception:  # noqa: BLE001
        logger.debug("Release session restore skipped", exc_info=True)
        st.session_state["_release_session_prompt_done"] = True

if st.session_state.get("_draft_scope_warning"):
    st.warning(
        "**Restored session — scope note:** "
        + str(st.session_state["_draft_scope_warning"])
        + " Your Release Notes / SHIPIT draft is kept; re-check tickets before deploy.",
        icon=":material/info:",
    )

if _mock_mode_enabled():
    st.warning(
        "**Mock mode enabled** — auth gate bypassed for UI development. "
        "Jira write operations (POST/PUT/DELETE) are blocked; reads still use credentials if set. "
        "Unset `MOCK_MODE` for normal operation.",
        icon=":material/science:",
    )

# ── Startup validation ───────────────────────────────────────────────
_startup_warnings: list[str] = []
if not os.path.isfile(ENV_FILE):
    _startup_warnings.append("`.env` file not found — credentials will need to be entered below.")
if not config.PROJECTS:
    _startup_warnings.append(
        "No projects configured in `workspace.yaml`. "
        "Go to **Settings** after connecting to add your Jira projects."
    )

# ── Auth gate ────────────────────────────────────────────────────────
has_token = bool(
    config.JIRA_EMAIL
    and config.JIRA_API_TOKEN
    and config.JIRA_API_TOKEN != "your-api-token-here"
) or _mock_mode_enabled()

if not has_token:
    inject_design_system()
    inject_theme_bootstrap()
    st.markdown("")
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.markdown("## \U0001f510 Connect to Jira")
        st.markdown(
            "One-time setup to link your Jira account.\n\n"
            "1. Open **[Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)**\n"
            "2. Click **Create API token** \u2192 name it `Release Tool`\n"
            "3. Paste it below"
        )
        for w in _startup_warnings:
            st.warning(w)
        st.markdown("")
        input_url = st.text_input(
            "Jira URL",
            value=config.JIRA_BASE_URL if config.JIRA_BASE_URL != "https://example.atlassian.net" else "",
            placeholder="https://yourorg.atlassian.net",
            help="Your organization's Atlassian cloud URL, e.g. https://yourorg.atlassian.net",
        )
        input_email = st.text_input(
            "Jira Email",
            value=config.JIRA_EMAIL or "",
            placeholder="you@company.com",
            help="The email address associated with your Atlassian account.",
        )
        input_token = st.text_input(
            "API Token",
            type="password",
            placeholder="Paste token here",
            help="Generate at https://id.atlassian.com/manage-profile/security/api-tokens",
        )
        st.markdown("")
        if st.button("\U0001f517 Connect", type="primary", use_container_width=True):
            if input_email and input_token:
                save_and_reload_env(input_email, input_token, input_url or None)
                st.success("Connected! Restarting...")
                st.rerun()
            else:
                st.error("Email and token are required.")
    st.stop()

# ── Page chrome ──────────────────────────────────────────────────────
inject_design_system()
inject_theme_bootstrap()

ss_default("wiz_step", 1)
ensure_ui_build_sync()

sidebar.render()

active_app = st.session_state.get("active_app")
render_app_header(active_app)

# ── Router (lazy imports — only load the module that's needed) ───────
if not active_app:
    home.render()

elif active_app == "settings":
    from release_platform.ui import settings
    settings.render()

elif active_app == "release_deployer":
    from release_platform.ui import (
        history,
        step1_release,
        step2_quick_tickets,
        step2_tickets,
        step3_deploy_info,
        step3_exclude_fix,
        step4_review,
        step5_execute,
    )
    from release_platform.ui.deployer_flow import is_quick_start, step_count, step_labels
    from release_platform.ui.deployment_dashboard import render_deployment_dashboard
    from release_platform.ui.workflow import render_app_prerequisite_gate, render_step_banner, render_workflow_status_strip

    if not render_app_prerequisite_gate("release_deployer"):
        st.stop()

    ss_default("wiz_draft_prompt_done", True)

    from release_platform.ui.workflow import disable_deployer_standalone, is_deployer_standalone

    if is_deployer_standalone():
        st.markdown(
            '<div class="jt-banner jt-banner--info" style="margin-bottom:12px">'
            "<strong>Quick start</strong> — post deployment comments without Ticket Review, "
            "Release Notes, or Service Ticket. "
            "<strong>Step 2:</strong> uncheck tickets that failed in production; "
            "the rest get comments and move to Done.</div>",
            unsafe_allow_html=True,
        )
        if st.button("Switch to full workflow", key="wiz_exit_standalone"):
            disable_deployer_standalone()
            st.rerun()
    else:
        render_workflow_status_strip()

    if ensure_deployer_wizard_version():
        st.info(
            "Release Deployer workflow was updated. Please start again from step 1.",
            icon=":material/info:",
        )

    step = st.session_state.get("wiz_step", 1)
    if step == -1:
        if st.button("\u2190 Back to Deployer", key="hist_back_top"):
            st.session_state["wiz_step"] = 1
            st.rerun()
        tab_history, tab_dashboard = st.tabs(["History", "Dashboard"])
        with tab_history:
            history.render_list(embedded=True)
        with tab_dashboard:
            render_deployment_dashboard()
    elif step == -2:
        history.render_detail()
    else:
        labels = step_labels()
        render_stepper(step, labels)
        render_step_banner("release_deployer", step, total_steps=step_count())
        if is_quick_start():
            if step == 1:
                step1_release.render()
            elif step == 2:
                step2_quick_tickets.render()
            elif step == 3:
                step3_deploy_info.render()
            elif step == 4:
                step4_review.render()
            elif step == 5:
                step5_execute.render()
            elif step > 5:
                st.session_state["wiz_step"] = 1
                st.rerun()
        else:
            if step == 1:
                step1_release.render()
            elif step == 2:
                step2_tickets.render()
            elif step == 3:
                step3_exclude_fix.render()
            elif step == 4:
                step3_deploy_info.render()
            elif step == 5:
                step4_review.render()
            elif step == 6:
                step5_execute.render()

elif active_app == "ticket_review":
    from release_platform.ui import ticket_review
    ticket_review.render()

elif active_app == "release_notes":
    from release_platform.ui import release_notes
    release_notes.render()

elif active_app == "service_ticket":
    from release_platform.ui import service_ticket
    service_ticket.render()

elif active_app == "ai_ticket_creator":
    from release_platform.ui import ai_ticket_creator
    ai_ticket_creator.render()

elif active_app == "jql_search":
    from release_platform.ui import jql_search
    jql_search.render()
