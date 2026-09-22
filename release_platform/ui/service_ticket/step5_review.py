"""Step 5 — Review all fields and create the SHIPIT service ticket."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import streamlit as st

import adf_builder as adf
import config
import jira_client
import ai_enhancer
import confluence_publisher
import release_stats
import release_critical as rc
import schedule_time
import shipit_test_mode
import slack_announce as sa
from release_platform.ui.helpers import derive_release_doc_metadata, esc, navigate_to_app, reset_app, sync_stk_plans_fingerprint
from release_platform.ui.teams_panel import render_teams_dual_schedule_panel
from teams_meeting_content import MeetingContext
from release_platform.ui.service_ticket.step2_details import _render_schedule
from release_platform.ui.workflow import (
    check_app_prerequisites,
    is_service_ticket_standalone,
    render_action_hint,
    service_ticket_create_blockers,
)

logger = logging.getLogger(__name__)


def _go(step: int) -> None:
    from release_platform.ui.service_ticket.nav import go_step

    go_step(step)


def _render_ai_enhancement(ss, extracted: list) -> None:
    """Render AI-generated summary, risk assessment, and acceptance criteria."""
    if not extracted:
        return

    with st.expander("AI-Enhanced Insights", expanded=False):
        st.caption(
            "AI-generated insights based on the tickets in this release. "
            "These are suggestions only — review before sharing."
        )

        cached_summary = ss.get("stk_ai_summary")
        cached_risk = ss.get("stk_ai_risk")

        c1, c2 = st.columns([2, 1])
        with c1:
            if st.button("Generate AI Summary", key="stk_ai_generate"):
                with st.spinner("Generating AI insights…"):
                    try:
                        ss["stk_ai_summary"] = ai_enhancer.summarize_ticket_set(extracted)
                        ss["stk_ai_risk"] = ai_enhancer.rate_release_risk(extracted).to_dict()
                    except Exception as exc:
                        st.error(f"AI enhancement failed: {exc}")
                st.rerun()
        with c2:
            if cached_summary and st.button("Clear", key="stk_ai_clear"):
                ss.pop("stk_ai_summary", None)
                ss.pop("stk_ai_risk", None)
                st.rerun()

        if cached_summary:
            st.markdown("**Executive Summary**")
            st.info(cached_summary)

        if cached_risk:
            risk_level = cached_risk.get("level", "unknown")
            risk_score = cached_risk.get("score", 0)
            risk_factors = cached_risk.get("factors", [])

            badge_color = {
                "low": "green",
                "medium": "orange",
                "high": "red",
            }.get(risk_level, "gray")
            st.markdown(
                f"**Risk Assessment:** "
                f'<span style="background:{badge_color};color:white;padding:2px 8px;border-radius:4px">'
                f"{risk_level.upper()} ({risk_score}%)</span>",
                unsafe_allow_html=True,
            )
            if risk_factors:
                st.markdown("**Risk Factors:**")
                for factor in risk_factors:
                    st.markdown(f"- {factor}")


def _text_to_adf(plain: str) -> dict:
    """Convert plain multi-line text to a single ADF paragraph with hardBreaks."""
    lines = plain.strip().splitlines()
    content: list[dict] = []
    for i, line in enumerate(lines):
        if i > 0:
            content.append(adf.hard_break())
        content.append(adf.text(line))
    return adf.doc(adf.paragraph(*content)) if content else adf.doc(adf.paragraph(adf.text(" ")))


def _multi_para_adf(plain: str) -> dict:
    """Convert SHIPIT plan text to ADF with bold phase headings."""
    return adf.shipit_plan_to_doc(plain)


def _jira_planned_isos(ss) -> tuple[str, str]:
    """IST (entered) window → Jira planned start/end ISO in US Central."""
    jira = schedule_time.resolve_jira_schedule(
        ss["stk_planned_start_date"],
        ss["stk_planned_start_time"],
        ss["stk_planned_end_date"],
        ss["stk_planned_end_time"],
        source_tz=ss.get("stk_schedule_tz") or config.TCKT_SCHEDULE_SOURCE_TZ,
        store_tz=config.TCKT_SCHEDULE_TZ,
    )
    return str(jira["start_iso"]), str(jira["end_iso"])


def render() -> None:
    ss = st.session_state

    # Success screen first — never show Create again once a ticket exists in this session.
    created_key = ss.get("stk_created_key")
    if created_key:
        if ss.pop("_stk_just_created", False):
            st.balloons()
            st.toast(f"Service ticket created: {created_key}", icon="🎫")
        _render_created_state(ss)
        return

    st.markdown("## Review & Create")
    _render_create_error(ss)

    summary = ss.get("stk_summary", "")
    extracted = ss.get("stk_extracted", [])
    desc_adf = ss.get("stk_description_adf")

    if not summary or not desc_adf:
        st.warning("Missing ticket data. Please go through all steps first.")
        if st.button("\u2190 Start Over"):
            _go(1)
        return

    # ── Field validation warnings ────────────────────────────────
    _validation_warnings = rc.service_ticket_review_warnings(dict(ss))
    if _validation_warnings:
        st.warning(
            "**Validation warnings** (you can still create the ticket):\n\n"
            + "\n".join(f"- {w}" for w in _validation_warnings)
        )

    st.markdown("### Ticket Summary")
    ss["stk_summary"] = st.text_input(
        "Summary (editable before create)",
        value=summary,
        key="_stk_review_summary",
        help="Uses Insights Customize BI Team in the auto-generated line.",
    )

    st.markdown("### Schedule")
    st.caption(
        "Edit the deployment window here if needed. Times are entered in IST by default; "
        "Jira shows approvers the equivalent in US Central."
    )
    _render_schedule(ss)
    sync_stk_plans_fingerprint()

    if ss.get("stk_test_mode") or shipit_test_mode.is_test_shipit_summary(summary):
        st.warning(
            "**TEST SHIPIT mode** — ticket will be created without approver groups or "
            "affected services (DO NOT DEPLOY)."
        )

    version_label, _ = derive_release_doc_metadata("rn_")
    if not version_label:
        version_label = str(ss.get("rn_version") or "").lstrip("vV")
    deploy_start = deploy_end = None
    if ss.get("stk_planned_start_date") and ss.get("stk_planned_start_time"):
        from datetime import datetime

        deploy_start = datetime.combine(
            ss["stk_planned_start_date"], ss["stk_planned_start_time"]
        )
    if ss.get("stk_planned_end_date") and ss.get("stk_planned_end_time"):
        from datetime import datetime

        deploy_end = datetime.combine(
            ss["stk_planned_end_date"], ss["stk_planned_end_time"]
        )
    render_teams_dual_schedule_panel(
        version=version_label or "release",
        review_context=MeetingContext(version=version_label or "", kind="review"),
        deployment_context=MeetingContext(version=version_label or "", kind="deployment"),
        deployment_start=deploy_start,
        deployment_end=deploy_end,
        timezone_name=str(ss.get("stk_schedule_tz") or config.TCKT_SCHEDULE_SOURCE_TZ),
    )

    st.markdown("### Classification")
    st.markdown(
        f"Change Type: **{esc(ss.get('stk_change_type', 'Normal'))}** | "
        f"Risk: **{esc(ss.get('stk_change_risk', 'Medium'))}** | "
        f"Impact: **{esc(ss.get('stk_impact') or 'Not set')}** | "
        f"Urgency: **{esc(ss.get('stk_urgency') or 'Not set')}**"
    )

    approvers = ss.get("stk_approvers") or config.TCKT_DEFAULTS.get("approvers", [])
    groups = ss.get("stk_approver_groups") or config.TCKT_DEFAULTS.get("approver_groups", [])
    assignment_group = (
        ss.get("stk_assignment_group")
        or config.TCKT_DEFAULTS.get("assignment_group", {})
    )
    team_id = ss.get("stk_team") or config.TCKT_DEFAULTS.get("team", "")
    team_name = config.TCKT_DEFAULTS.get("team_name", "")
    assignment_group_name = config.TCKT_DEFAULTS.get("assignment_group_name", "")

    st.markdown("### Routing & Approvals")
    assignment_group_label = assignment_group_name or assignment_group.get(
        "value", assignment_group.get("id", "—")
    )
    st.markdown(f"**Assignment Group:** {esc(assignment_group_label)}")
    st.markdown(f"**Team:** {esc(team_name or team_id or '—')}")
    st.markdown("### Approvers & Groups")
    if approvers:
        st.markdown(
            "**Approvers:** "
            + ", ".join(
                esc(str(a.get("accountId", a))) for a in approvers if isinstance(a, dict)
            )
        )
    if groups:
        st.markdown(
            "**Groups:** "
            + ", ".join(
                esc(g.get("name") if isinstance(g, dict) else str(g)) for g in groups
            )
        )
    validation = ss.get("stk_approver_validation")
    if validation is not None and not validation.all_ok:
        st.warning("Approver validation failed — go back to Step 2 and fix assignments.")

    st.markdown(f"### Tickets Included: {len(extracted)}")

    # ── AI Enhancement Panel ─────────────────────────────────────
    _render_ai_enhancement(ss, extracted)

    st.markdown("### Plans")
    for label, key in [
        ("Implementation", "stk_impl_plan"),
        ("Test", "stk_test_plan"),
        ("Backout", "stk_backout_plan"),
        ("Business Impact", "stk_business_impact"),
    ]:
        with st.expander(f"{label} Plan", expanded=False):
            st.text(ss.get(key, ""))

    st.markdown("")

    if is_service_ticket_standalone():
        st.info(
            "**Quick start mode** — Ticket Review lock-in and in-app Release Notes generation "
            "are not required. SharePoint link + loaded tickets are enough to create the SHIPIT ticket."
        )

    blockers = service_ticket_create_blockers(dict(ss))
    if blockers:
        st.error("**Cannot create SHIPIT ticket yet.** Fix these items first:")
        for item in blockers:
            st.markdown(f"- {esc(item)}")

    st.markdown(
        '<div class="jt-banner jt-banner--info" style="margin:12px 0">'
        "<strong>Before creating:</strong> You can go back to any step to edit summary, "
        "description, plans, or classification. After creation, use "
        "<strong>Edit draft & create new SHIPIT ticket</strong> if you need a corrected ticket."
        "</div>",
        unsafe_allow_html=True,
    )

    is_test = bool(ss.get("stk_test_mode")) or shipit_test_mode.is_test_shipit_summary(
        str(ss.get("stk_summary") or "")
    )
    confirm_label = (
        "I have reviewed this TEST SHIPIT draft (DO NOT DEPLOY — demo/migration validation only)."
        if is_test
        else "I have reviewed everything above and understand this will create a real Jira change ticket."
    )
    confirm = st.checkbox(confirm_label, key="stk_create_confirm")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("\u2190 Back", key="stk_s5_back"):
            _go(5)
    with c2:
        if st.button("Restart from Step 1", key="stk_restart_step1"):
            reset_app("service_ticket")
    with c3:
        creating = bool(ss.get("_stk_creating"))
        can_create = not blockers and confirm and not creating
        if st.button(
            "\U0001f3ab Create SHIPIT Ticket",
            type="primary",
            key="stk_create",
            disabled=not can_create,
        ):
            _create_ticket(ss)
    if creating:
        render_action_hint("Creating TCKT in Jira — please wait, do not click again.")
    elif not (not blockers and confirm):
        render_action_hint(
            "Resolve all blockers and check the confirmation box to enable creation."
        )
    else:
        render_action_hint(
            "Creates the TCKT in Jira. After success, continue to Release Deployer."
        )


def _find_existing_after_failure(summary: str) -> dict | None:
    """After a failed create, check whether the ticket was raised anyway.

    Removes the "did it go through or not?" ambiguity that otherwise tempts a retry
    and produces a duplicate change ticket.
    """
    try:
        issue = jira_client.find_tckt_by_summary(summary)
    except Exception:
        # A diagnostic must never mask the failure it is explaining.
        logger.debug("Duplicate check after create failure did not run", exc_info=True)
        return None
    if not issue:
        return None
    key = str(issue.get("key") or "")
    if not key:
        return None
    return {"key": key, "url": f"{config.JIRA_BASE_URL}/browse/{key}"}


def _describe_create_failure(exc: Exception) -> dict:
    """Capture a create failure in a form the review page can render after a rerun."""
    field_errors = dict(getattr(exc, "field_errors", {}) or {})
    return {
        "message": str(exc),
        "status_code": getattr(exc, "status_code", None),
        "field_errors": {
            jira_client.field_label(field_id): reason
            for field_id, reason in sorted(field_errors.items())
        },
    }


def _render_create_error(ss) -> None:
    error = ss.get("_stk_create_error")
    if not error:
        return

    status = error.get("status_code")
    heading = (
        f"Ticket was not created (HTTP {status})." if status
        else "Ticket was not created."
    )
    st.error(f"**{heading}**\n\n{error.get('message', '')}")

    field_errors = error.get("field_errors") or {}
    if field_errors:
        st.markdown(
            "**Fields Jira rejected**\n\n"
            + "\n".join(f"- `{esc(name)}` — {esc(reason)}" for name, reason in field_errors.items())
        )
        st.caption(
            "Correct these values on the earlier wizard steps, or update the field "
            "mapping under service_desk.fields in workspace.yaml, then try again."
        )
    elif status == 400:
        st.caption(
            "Jira did not name a specific field. Check that the Service Desk ID and "
            "Request Type ID in Settings match the TCKT change request form."
        )

    existing = error.get("existing")
    if existing:
        st.warning(
            f"**A TCKT with this summary already exists: {existing['key']}.** "
            "The ticket was raised before the failure, so do not click Create "
            "again — open it and check its fields instead."
        )
        st.markdown(f"[Open {esc(existing['key'])} in Jira]({esc(existing['url'])})")
    elif "existing" in error:
        st.info(
            "Checked Jira: no change ticket with this summary was created, "
            "so it is safe to fix the problem above and try again."
        )

    if st.button("Dismiss error", key="stk_dismiss_create_error"):
        ss.pop("_stk_create_error", None)
        st.rerun()


def _schedule_window(ss) -> dict[str, str]:
    """Dual-timezone window wording for description, plans, and ticket comment."""
    start_d = ss.get("stk_planned_start_date")
    start_t = ss.get("stk_planned_start_time")
    end_d = ss.get("stk_planned_end_date")
    end_t = ss.get("stk_planned_end_time")
    if not (start_d and start_t and end_d and end_t):
        return {}
    return schedule_time.window_statement(
        start_d, start_t, end_d, end_t,
        tz_name=ss.get("stk_schedule_tz") or config.TCKT_SCHEDULE_SOURCE_TZ,
        display_tz=config.TCKT_DISPLAY_TZ,
    )


def _render_schedule_review(ss) -> None:
    """Planned window in the entered zone and in the reviewers' zone."""
    start_d = ss.get("stk_planned_start_date")
    start_t = ss.get("stk_planned_start_time")
    end_d = ss.get("stk_planned_end_date")
    end_t = ss.get("stk_planned_end_time")
    if not (start_d and start_t and end_d and end_t):
        st.markdown("_Schedule is incomplete._")
        return

    tz_name = ss.get("stk_schedule_tz") or config.TCKT_SCHEDULE_SOURCE_TZ
    info = schedule_time.describe_window(
        start_d, start_t, end_d, end_t,
        tz_name=tz_name,
        display_tz=config.TCKT_DISPLAY_TZ,
    )
    jira = schedule_time.resolve_jira_schedule(
        start_d, start_t, end_d, end_t,
        source_tz=tz_name,
        store_tz=config.TCKT_SCHEDULE_TZ,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"**Entered ({esc(tz_name)}):**<br/>"
            f"{esc(str(info['entered_start']))} \u2192 {esc(str(info['entered_end']))}",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"**Jira shows ({esc(str(info['display_timezone']))}):**<br/>"
            f"{esc(str(info['display_start']))} \u2192 {esc(str(info['display_end']))}",
            unsafe_allow_html=True,
        )

    if info["valid"]:
        st.caption(
            f"Window length {schedule_time.duration_label(int(info['duration_minutes']))}. "
            f"Jira planned start/end fields: {jira['start_iso']} \u2192 {jira['end_iso']} "
            f"({jira['reviewer_range']})."
        )
    if info["display_crosses_day"] and not info["same_zone"]:
        st.info(
            "In the reviewers' timezone this window spans midnight. The instant "
            "is correct; state the local time in the plans so it does not read "
            "as an unplanned overnight change."
        )


def _render_confluence_publish(ss, ticket_key: str) -> None:
    """Render optional Confluence publish button after TCKT creation."""
    confluence_space = os.environ.get("CONFLUENCE_SPACE", "")
    confluence_parent = os.environ.get("CONFLUENCE_PARENT_ID", "")

    if not confluence_space:
        st.info(
            "Confluence publishing is disabled. Set `CONFLUENCE_SPACE` and optionally "
            "`CONFLUENCE_PARENT_ID` in `.env` to enable."
        )
        return

    st.markdown("### Publish to Confluence")
    st.caption("Optionally publish release notes as a Confluence wiki page.")

    if ss.get("stk_confluence_published"):
        result = ss.get("stk_confluence_result", {})
        page_url = result.get("url", "")
        st.success("Confluence page published successfully.")
        if page_url:
            st.markdown(f"[Open Confluence page]({page_url})")
        return

    if ss.get("stk_confluence_error"):
        st.error(f"Confluence publish failed: {esc(ss['stk_confluence_error'])}")
        if st.button("Clear error", key="stk_confluence_clear_error"):
            ss.pop("stk_confluence_error", None)
            st.rerun()

    with st.expander("Confluence settings", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            space = st.text_input(
                "Space key",
                value=ss.get("stk_confluence_space", confluence_space),
                key="_stk_confluence_space",
            )
            ss["stk_confluence_space"] = space
        with c2:
            parent = st.text_input(
                "Parent page ID (optional)",
                value=ss.get("stk_confluence_parent", confluence_parent),
                key="_stk_confluence_parent",
            )
            ss["stk_confluence_parent"] = parent

    ticket_data = {
        "ticket_key": ticket_key,
        "summary": ss.get("stk_summary", ""),
        "sharepoint_url": ss.get("stk_sharepoint", ""),
        "extracted": ss.get("stk_extracted", []),
        "implementation_plan": ss.get("stk_impl_plan", ""),
        "test_plan": ss.get("stk_test_plan", ""),
        "backout_plan": ss.get("stk_backout_plan", ""),
        "business_impact": ss.get("stk_business_impact", ""),
    }

    if st.button("Publish to Confluence", key="stk_confluence_publish"):
        space = ss.get("stk_confluence_space", confluence_space)
        parent = ss.get("stk_confluence_parent", confluence_parent) or None
        with st.spinner("Publishing to Confluence…"):
            body = confluence_publisher.generate_page_body(ticket_data)
            title = confluence_publisher.default_title(ticket_data)
            result = confluence_publisher.publish_page(space, parent, body, title=title)
        if result.ok:
            ss["stk_confluence_published"] = True
            ss["stk_confluence_result"] = result.to_dict()
            ss.pop("stk_confluence_error", None)
        else:
            ss["stk_confluence_error"] = result.error
        st.rerun()


def _render_created_state(ss) -> None:
    key = ss["stk_created_key"]
    url = f"{config.JIRA_BASE_URL}/browse/{key}"
    st.markdown("## Review & Create")
    st.markdown(
        f'<div class="stk-created-banner">'
        f'<div class="stk-created-banner__icon">\u2705</div>'
        f'<h2>Ticket Created Successfully</h2>'
        f'<p style="font-size:1.15rem;margin:12px 0 4px 0">'
        f'<a href="{esc(url)}" target="_blank" class="jt-link">'
        f'{esc(key)}</a></p>'
        f'<p style="font-size:.92rem">'
        f'This ticket is live in Jira. The create button is disabled to prevent duplicates.'
        f"</p></div>",
        unsafe_allow_html=True,
    )
    st.success(
        f"Ticket **{key}** was created successfully in Jira and is ready to share."
    )
    st.markdown(f"**Ticket link** — [{esc(key)}]({esc(url)})", unsafe_allow_html=False)
    st.code(url, language=None)
    st.caption("Copy this URL to share the change ticket with approvers.")

    post_warning = ss.pop("_stk_post_create_warning", None)
    if post_warning:
        st.warning(
            f"The ticket was created, but some follow-up steps need attention: {esc(post_warning)}"
        )

    # ── Request Type status (hardened) ──────────────────────────
    rt_status = ss.get("stk_rt_status")
    if rt_status and getattr(rt_status, "ok", False):
        st.success(getattr(rt_status, "message", None) or "Request Type was set automatically.")
    else:
        message = getattr(rt_status, "message", "") if rt_status else (
            "Request Type was not configured. Configure TCKT_SERVICE_DESK_ID and "
            "TCKT_REQUEST_TYPE_ID to enable auto-set."
        )
        rt_label = config.TCKT_REQUEST_TYPE_NAME or "Submit A Normal or Emergency Change"
        st.markdown(
            f'<div class="stk-error-panel">'
            f'<strong>Request Type could not be set automatically.</strong><br/>'
            f'{esc(message)}<br/><br/>'
            f'<strong>Manual steps:</strong> Go to Details panel → Request Type → '
            f'<em>"{esc(rt_label)}"</em>.</div>',
            unsafe_allow_html=True,
        )
        if st.button("Retry Request Type", key="stk_retry_request_type"):
            with st.spinner("Setting Request Type…"):
                ss["stk_rt_status"] = jira_client.set_request_type_detailed(key)
                ss["stk_rt_auto_set"] = ss["stk_rt_status"].ok
            st.rerun()
    st.code(url, language=None)
    st.caption("Click the box above to copy the Jira URL.")

    _render_assignment_status(ss, key)

    summary_text = str(ss.get("stk_summary") or "")
    if shipit_test_mode.is_test_shipit_summary(summary_text):
        st.markdown("### Dispose TEST SHIPIT")
        st.caption("MCP parity: `dispose test shipit SHIPIT-XXXX` — comment, cancel, delete.")
        if st.button("Dispose this TEST ticket", key="stk_dispose_test", type="secondary"):
            with st.spinner("Disposing TEST SHIPIT…"):
                result = jira_client.dispose_test_shipit_ticket(key)
            if result.get("status") == "ok":
                st.success(result.get("message") or "TEST ticket disposed.")
                ss.pop("stk_created_key", None)
                ss.pop("stk_created_url", None)
            else:
                st.error(result.get("error") or result.get("message") or "Dispose failed.")
            st.rerun()

    if ss.get("stk_schedule_comment_ok"):
        st.success(
            "Deployment window comment posted on the ticket "
            "(IST agreed window + how Planned start/end appear in US Central)."
        )
    elif ss.get("stk_schedule_comment_error"):
        st.warning(
            "Ticket created, but the timezone clarification comment was not posted: "
            f"{esc(ss['stk_schedule_comment_error'])}. "
            "Add it manually from the Deployment Window section in Description / Implementation Plan."
        )
        if st.button("Retry window comment", key="stk_retry_schedule_comment"):
            window = _schedule_window(ss)
            if window:
                try:
                    jira_client.add_schedule_window_comment(key, window)
                    ss["stk_schedule_comment_ok"] = True
                    ss.pop("stk_schedule_comment_error", None)
                except Exception as exc:
                    ss["stk_schedule_comment_error"] = str(exc)
            st.rerun()

    # ── Confluence publishing (optional) ────────────────────────
    _render_confluence_publish(ss, key)

    # ── Slack announce (before Release Deployer) ────────────────
    _render_slack_announce(ss, key, url)

    slack_cfg = sa.load_announce_config(
        {"slack_announce": config.SLACK_ANNOUNCE} if config.SLACK_ANNOUNCE else {}
    )
    slack_applies = sa.slack_gate_applies(slack_cfg)
    slack_done = sa.deployer_slack_gate_open(
        enabled=slack_applies,
        sent=bool(ss.get("stk_slack_sent")),
        skipped=bool(ss.get("stk_slack_skipped")),
        can_send=slack_cfg.can_send(),
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("\U0001f3e0 Home", key="stk_done_home"):
            st.session_state.pop("active_app", None)
            for k in list(st.session_state.keys()):
                if k.startswith(("stk_", "_stk_")):
                    del st.session_state[k]
            st.rerun()
    with c2:
        if st.button("Edit draft & create new SHIPIT ticket", key="stk_edit_recreate"):
            for state_key in (
                "stk_created_key",
                "stk_create_confirm",
                "stk_rt_status",
                "stk_rt_auto_set",
                "stk_confluence_published",
                "stk_slack_sent",
                "stk_slack_skipped",
                "stk_slack_results",
                "stk_assignment_warnings",
                "stk_assignment_autofix_done",
                "stk_schedule_comment_ok",
                "stk_schedule_comment_error",
            ):
                ss.pop(state_key, None)
            _go(2)
    with c3:
        deploy_ready = check_app_prerequisites("release_deployer").ok
        if slack_cfg.enabled and not slack_done:
            st.caption("Send or skip the Slack announce above, then continue.")
        if st.button(
            "Release Deployer \u2192",
            type="primary",
            key="stk_done_next_app",
            disabled=not deploy_ready or not slack_done,
        ):
            navigate_to_app("release_deployer")
        if deploy_ready and slack_done:
            render_action_hint(
                "Opens Release Deployer to post deployment comments and transition tickets."
            )
        elif not slack_done:
            render_action_hint(
                "Preview and send (or skip) the Slack announce to both channels first."
            )
        else:
            render_action_hint("TCKT must be created successfully before post-deploy steps.")


def _assignment_expectations(ss) -> dict[str, Any]:
    defaults = config.TCKT_DEFAULTS
    return {
        "approvers": ss.get("stk_approvers") or defaults.get("approvers", []),
        "approver_groups": ss.get("stk_approver_groups") or defaults.get(
            "approver_groups", []
        ),
        "team": ss.get("stk_team") or "",
        "assignment_group": ss.get("stk_assignment_group") or defaults.get(
            "assignment_group", {}
        ),
        "change_type": config.resolve_tckt_select(
            "change_type", ss.get("stk_change_type", "Normal"),
        ),
    }


def _reapply_assignments(ss, issue_key: str) -> tuple[list[str], list[str]]:
    """Re-apply approvers / groups / team via REST edit, then re-verify."""
    cf = config.TCKT_FIELDS
    exp = _assignment_expectations(ss)
    fields: dict[str, Any] = {}
    if cf.get("approvers") and exp["approvers"]:
        fields[cf["approvers"]] = exp["approvers"]
    if cf.get("approver_groups") and exp["approver_groups"]:
        fields[cf["approver_groups"]] = exp["approver_groups"]
    if cf.get("team") and exp["team"]:
        fields[cf["team"]] = exp["team"]
    if cf.get("assignment_group") and exp["assignment_group"]:
        fields[cf["assignment_group"]] = exp["assignment_group"]
    if cf.get("change_type") and exp["change_type"]:
        fields[cf["change_type"]] = exp["change_type"]

    apply_warnings = jira_client.apply_supplemental_tckt_fields(issue_key, fields)
    verify = _verify_assignments(
        issue_key,
        exp["approvers"],
        exp["approver_groups"],
        expected_team=exp["team"],
        expected_assignment_group=exp["assignment_group"],
    )
    return apply_warnings, verify


def _render_assignment_status(ss, issue_key: str) -> None:
    """Show assignment verification and offer fix when post-create edit failed."""
    warnings = list(ss.get("stk_assignment_warnings") or [])

    # One automatic repair attempt for tickets created before the Team/batch fix.
    if warnings and not ss.get("stk_assignment_autofix_done"):
        ss["stk_assignment_autofix_done"] = True
        with st.spinner("Re-applying approvers, groups, and team…"):
            apply_warnings, verify = _reapply_assignments(ss, issue_key)
        ss["stk_assignment_warnings"] = verify
        if apply_warnings:
            ss["_stk_post_create_warning"] = "; ".join(apply_warnings)
        st.rerun()
        return

    if warnings:
        st.warning(
            "**Assignment verification:**\n\n"
            + "\n".join(f"- {esc(w)}" for w in warnings)
            + "\n\nClick **Fix assignments** to re-apply Approvers, Approver Groups, "
            "Team, and Change Type from this draft."
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Fix assignments", type="primary", key="stk_fix_assignments"):
                with st.spinner("Re-applying approvers, groups, and team…"):
                    apply_warnings, verify = _reapply_assignments(ss, issue_key)
                ss["stk_assignment_warnings"] = verify
                if apply_warnings:
                    st.error("Some updates failed: " + "; ".join(apply_warnings))
                st.rerun()
        with c2:
            if st.button("Re-check from Jira", key="stk_recheck_assignments"):
                exp = _assignment_expectations(ss)
                with st.spinner("Reading ticket from Jira…"):
                    ss["stk_assignment_warnings"] = _verify_assignments(
                        issue_key,
                        exp["approvers"],
                        exp["approver_groups"],
                        expected_team=exp["team"],
                        expected_assignment_group=exp["assignment_group"],
                    )
                st.rerun()
    else:
        st.success(
            "Assignment Group, Team, approvers, and approver groups verified on the created ticket."
        )
        if st.button("Re-check assignments", key="stk_recheck_assignments_ok"):
            exp = _assignment_expectations(ss)
            with st.spinner("Reading ticket from Jira…"):
                ss["stk_assignment_warnings"] = _verify_assignments(
                    issue_key,
                    exp["approvers"],
                    exp["approver_groups"],
                    expected_team=exp["team"],
                    expected_assignment_group=exp["assignment_group"],
                )
            st.rerun()


def _render_slack_announce(ss, ticket_key: str, ticket_url: str) -> None:
    """Preview + send deployment Slack posts to squad and bi-buddies."""
    if config.slack_archived():
        st.caption(
            "Slack announce is archived for this workspace. "
            "Restore from `archive/slack_announce.yaml` when ready."
        )
        return

    cfg = sa.load_announce_config(
        {"slack_announce": config.SLACK_ANNOUNCE} if config.SLACK_ANNOUNCE else {}
    )
    if not cfg.enabled:
        st.info(
            "Slack announce is disabled (`slack_announce.enabled=false`). "
            "You can continue to Release Deployer without sending."
        )
        return

    if not cfg.can_send():
        st.info(
            "Slack announce is configured but **SLACK_BOT_TOKEN** is missing or the bot "
            "is not invited to the channels. Preview messages below for copy/paste, or "
            "continue to Release Deployer — sending is optional until IT completes setup."
        )

    st.markdown("### Send Slack message")
    st.caption(
        "After the service ticket and approvers are set, announce the upcoming deployment "
        "in **#insights-customize-squad** and **#customize-bi-buddies**. "
        "Preview both messages (with CC tags) before sending. "
        "Then continue to Release Deployer. "
        "Uses the Bot API (`SLACK_BOT_TOKEN`) — not the legacy `SLACK_DEPLOY_WEBHOOK`."
    )

    if ss.get("stk_slack_sent"):
        results = ss.get("stk_slack_results") or []
        st.success("Slack announcements sent.")
        for r in results:
            if getattr(r, "ok", False):
                link = getattr(r, "permalink", "") or ""
                label = f"#{getattr(r, 'channel_name', '')}"
                if link:
                    st.markdown(f"- {label} — [open message]({link})")
                else:
                    st.markdown(f"- {label} — sent")
            else:
                st.error(
                    f"#{getattr(r, 'channel_name', '')}: {getattr(r, 'error', 'failed')}"
                )
        return

    if ss.get("stk_slack_skipped"):
        st.info("Slack announce skipped for this ticket. You can continue to Release Deployer.")
        if st.button("Show Slack preview again", key="stk_slack_unskip"):
            ss.pop("stk_slack_skipped", None)
            st.rerun()
        return

    draft = sa.draft_from_session(
        ticket_key=ticket_key,
        summary=str(ss.get("stk_summary") or ""),
        ticket_url=ticket_url,
        planned_start=ss.get("stk_planned_start_date"),
        sharepoint_url=str(ss.get("stk_sharepoint") or ""),
        version_hint=str(ss.get("stk_version") or ""),
    )

    # Seed editable session fields once.
    if "stk_slack_deploy_date" not in ss:
        ss["stk_slack_deploy_date"] = draft.deploy_date
    if "stk_slack_version" not in ss:
        ss["stk_slack_version"] = draft.version
    if "stk_slack_sharepoint" not in ss:
        ss["stk_slack_sharepoint"] = draft.sharepoint_url
    if "stk_slack_environments" not in ss:
        ss["stk_slack_environments"] = draft.environments
    if "stk_slack_init_ticket" not in ss:
        ss["stk_slack_init_ticket"] = ticket_key

    snapshot = ss.get("shared_snapshot") or {}
    ticket_count = len(
        snapshot.get("ticket_keys")
        or snapshot.get("issues")
        or []
    )

    regen_col, _ = st.columns([1, 3])
    with regen_col:
        if st.button("Regenerate from template", key="stk_slack_regen"):
            fresh = sa.draft_from_session(
                ticket_key=ticket_key,
                summary=str(ss.get("stk_summary") or ""),
                ticket_url=ticket_url,
                planned_start=ss.get("stk_planned_start_date"),
                sharepoint_url=str(ss.get("stk_sharepoint") or ""),
                version_hint=str(ss.get("stk_version") or ""),
            )
            ss["stk_slack_deploy_date"] = fresh.deploy_date
            ss["stk_slack_version"] = fresh.version
            ss["stk_slack_sharepoint"] = fresh.sharepoint_url
            ss.pop("stk_slack_body_overrides", None)
            st.rerun()

    with st.expander("Edit announcement details", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            ss["stk_slack_deploy_date"] = st.date_input(
                "Deployment date",
                value=ss["stk_slack_deploy_date"],
                key="_stk_slack_deploy_date",
            )
            ss["stk_slack_version"] = st.text_input(
                "Release version (e.g. v2026.3.08.05)",
                value=ss["stk_slack_version"],
                key="_stk_slack_version",
            )
        with c2:
            ss["stk_slack_environments"] = st.text_input(
                "Environments phrase",
                value=ss["stk_slack_environments"],
                key="_stk_slack_environments",
                help="Appears after “for the …” in the message body.",
            )
            ss["stk_slack_sharepoint"] = st.text_input(
                "SharePoint release notes URL",
                value=ss["stk_slack_sharepoint"],
                key="_stk_slack_sharepoint",
            )

    live = sa.SlackAnnounceDraft(
        ticket_key=draft.ticket_key,
        ticket_summary=draft.ticket_summary,
        ticket_url=draft.ticket_url,
        version=str(ss["stk_slack_version"] or draft.version),
        deploy_date=ss["stk_slack_deploy_date"] or draft.deploy_date,
        sharepoint_url=str(ss["stk_slack_sharepoint"] or ""),
        sharepoint_label=sa.sharepoint_label_from_url(
            str(ss["stk_slack_sharepoint"] or ""),
            str(ss["stk_slack_version"] or draft.version),
        ),
        environments=str(ss["stk_slack_environments"] or draft.environments),
        ticket_count=ticket_count,
    )
    body_overrides = dict(ss.get("stk_slack_body_overrides") or {})
    messages = sa.build_channel_messages(live, cfg.channels, body_overrides=body_overrides)
    prior_results = list(ss.get("stk_slack_results") or [])
    pending = sa.pending_channel_messages(messages, prior_results)
    partial = bool(prior_results) and bool(pending) and not all(
        getattr(r, "ok", False) for r in prior_results
    )

    if prior_results and not ss.get("stk_slack_sent"):
        st.markdown("#### Previous send status")
        for r in prior_results:
            if getattr(r, "ok", False):
                st.success(f"#{r.channel_name}: already sent (will not be posted again)")
            else:
                st.error(f"#{r.channel_name}: {r.error or 'failed'}")

    st.markdown("#### Preview")
    show = pending if partial else messages
    overrides = dict(ss.get("stk_slack_body_overrides") or {})
    for msg in show:
        cc_names = ", ".join(p.display() for p in msg.channel.cc) or "(none)"
        st.markdown(
            f"**#{esc(msg.channel.name)}** — CC: {esc(cc_names)}"
        )
        custom = st.text_area(
            f"Message body (#{msg.channel.name})",
            value=overrides.get(msg.channel.key) or msg.preview,
            key=f"stk_slack_body_{msg.channel.key}",
            height=220,
            help="Edit before send. CC line is re-appended automatically on send.",
        )
        if custom.strip() and custom.strip() != msg.preview.strip():
            overrides[msg.channel.key] = custom
        elif msg.channel.key in overrides:
            overrides.pop(msg.channel.key, None)
    ss["stk_slack_body_overrides"] = overrides

    can_send = cfg.can_send()
    config_issues = sa.validate_announce_config(cfg)
    for issue in config_issues:
        if issue.level == "error":
            st.error(issue.message)
        else:
            st.warning(issue.message)
    sp_url = str(ss.get("stk_slack_sharepoint") or "")
    if sp_url.strip():
        from release_platform.ui.helpers import validate_sharepoint_url
        from sharepoint_url import sharepoint_validation_message

        if not validate_sharepoint_url(sp_url):
            st.error(
                sharepoint_validation_message(sp_url)
                or "SharePoint URL looks invalid."
            )
    if not can_send:
        st.warning(
            "Sending needs `SLACK_BOT_TOKEN` in `.env` and the bot invited to both channels. "
            "Add channel IDs under `slack_announce.channel_ids` in `workspace.yaml` if name "
            "lookup fails (common for private channels). You can still copy the preview text, "
            "or skip and continue."
        )

    confirm_label = (
        "I reviewed the failed-channel preview(s) and want to retry only those now"
        if partial
        else "I reviewed both previews (including CC tags) and want to send them now"
    )
    confirm = st.checkbox(
        confirm_label,
        key="stk_slack_confirm_send",
        disabled=not can_send,
    )

    send_label = (
        "Retry failed Slack channel(s)"
        if partial
        else "Send to both Slack channels"
    )
    b1, b2 = st.columns(2)
    with b1:
        if st.button(
            send_label,
            type="primary",
            key="stk_slack_send",
            disabled=not (can_send and confirm and (pending or messages)),
        ):
            with st.spinner(
                "Posting failed channels to Slack…"
                if partial
                else "Posting to Slack…"
            ):
                send_messages = sa.build_channel_messages(
                    live,
                    cfg.channels,
                    body_overrides=dict(ss.get("stk_slack_body_overrides") or {}),
                )
                to_send = sa.pending_channel_messages(send_messages, prior_results)
                new_results = sa.send_announce_messages(cfg, to_send)
            merged = sa.merge_send_results(prior_results, new_results)
            ss["stk_slack_results"] = merged
            if all(r.ok for r in merged):
                ss["stk_slack_sent"] = True
                from session_persist import persist_session

                persist_session(dict(ss))
                st.rerun()
            else:
                for r in new_results:
                    if r.ok:
                        st.success(f"#{r.channel_name}: sent")
                    else:
                        st.error(f"#{r.channel_name}: {r.error}")
    with b2:
        if st.button("Skip Slack announce", key="stk_slack_skip"):
            ss["stk_slack_skipped"] = True
            from session_persist import persist_session

            persist_session(dict(ss))
            st.rerun()


def _team_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return str(value or "")


def _assignment_group_key(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("name"):
            return str(value["name"]).casefold()
        return str(value.get("id") or "").casefold()
    return str(value or "").casefold()


def _verify_assignments(
    issue_key: str,
    expected_approvers: list,
    expected_groups: list,
    *,
    expected_team: Any = None,
    expected_assignment_group: Any = None,
) -> list[str]:
    """Compare created ticket approvers/groups against what we intended."""
    from diff_engine import extract_ticket_fields

    mismatches: list[str] = []
    try:
        issue = jira_client.get_issue(issue_key)
        actual = extract_ticket_fields(issue)
    except Exception as exc:
        return [f"Could not verify assignments: {exc}"]

    exp_a = {
        str(a.get("accountId") or a.get("account_id") or "")
        for a in (expected_approvers or [])
        if isinstance(a, dict)
    } - {""}
    act_raw = actual.get("approvers") or []
    if isinstance(act_raw, dict):
        act_raw = [act_raw]
    act_a = {
        str(a.get("accountId") or "")
        for a in act_raw
        if isinstance(a, dict)
    } - {""}
    if exp_a and exp_a != act_a:
        mismatches.append(
            f"Approvers mismatch — expected {len(exp_a)}, got {len(act_a)} on the ticket."
        )

    exp_g = {
        str(g.get("name") if isinstance(g, dict) else g)
        for g in (expected_groups or [])
    } - {""}
    act_g_raw = actual.get("approver_groups") or []
    if isinstance(act_g_raw, dict):
        act_g_raw = [act_g_raw]
    act_g = {
        str(g.get("name") or "")
        for g in act_g_raw
        if isinstance(g, dict)
    } - {""}
    if exp_g and exp_g != act_g:
        mismatches.append(
            f"Approver groups mismatch — expected {', '.join(sorted(exp_g))}; "
            f"got {', '.join(sorted(act_g)) or 'none'}."
        )

    cf = config.TCKT_FIELDS
    raw_fields = issue.get("fields", {}) or {}
    exp_team = _team_id(expected_team)
    if exp_team:
        team_cf = cf.get("team", "")
        actual_team = raw_fields.get(team_cf) if team_cf else None
        act_team = _team_id(actual_team)
        if act_team != exp_team:
            mismatches.append(
                f"Team mismatch — expected {exp_team}, got {act_team or 'none'}."
            )

    exp_ag = _assignment_group_key(expected_assignment_group)
    if exp_ag:
        ag_cf = cf.get("assignment_group", "")
        actual_ag = raw_fields.get(ag_cf) if ag_cf else None
        act_ag = _assignment_group_key(actual_ag)
        if act_ag != exp_ag:
            mismatches.append(
                f"Assignment Group mismatch — expected {exp_ag}, got {act_ag or 'none'}."
            )

    return mismatches


def _create_ticket(ss) -> None:
    if ss.get("stk_created_key"):
        st.warning(f"Ticket already created: **{ss['stk_created_key']}**")
        st.rerun()
        return
    if ss.get("_stk_creating"):
        return

    ss["_stk_creating"] = True
    summary = ss["stk_summary"]
    is_test = bool(ss.get("stk_test_mode")) or shipit_test_mode.is_test_shipit_summary(summary)
    if is_test:
        version_hint = str(ss.get("rn_version") or summary or "").lstrip("vV")
        if version_hint and not shipit_test_mode.is_test_shipit_summary(summary):
            summary = shipit_test_mode.default_test_summary(version_hint)
            ss["stk_summary"] = summary
    extracted = ss.get("stk_extracted", [])
    from release_platform.ui.service_ticket.step3_description import sync_description_adf

    desc_adf = sync_description_adf(extracted, ss.get("stk_sharepoint", ""))
    ss["stk_description_adf"] = desc_adf

    impl_adf = _text_to_adf(ss.get("stk_impl_plan", ""))
    test_adf = _multi_para_adf(ss.get("stk_test_plan", ""))
    backout_adf = _text_to_adf(ss.get("stk_backout_plan", ""))
    impact_adf = _multi_para_adf(ss.get("stk_business_impact", ""))
    comm_adf = _multi_para_adf(ss.get("stk_communication_plan", ""))
    reason_text = str(ss.get("stk_reason_for_change") or "").strip()

    cf = config.TCKT_FIELDS
    defaults = config.TCKT_DEFAULTS
    approvers = ss.get("stk_approvers") or defaults.get("approvers", [])
    approver_groups = ss.get("stk_approver_groups") or defaults.get("approver_groups", [])
    assignment_group = (
        ss.get("stk_assignment_group")
        or jira_client.resolve_assignment_group_value(defaults)
        or {}
    )
    # SHIPIT-16769 parity: approver groups only — do not default Team from workspace.yaml.
    team_value = ss.get("stk_team") or ""

    impl_key = config.service_desk_field("implementation_steps")
    test_key = config.service_desk_field("verification_steps")
    backout_key = config.service_desk_field("rollback_steps")

    start_iso, end_iso = _jira_planned_isos(ss)

    fields = {
        "description": desc_adf,
        "priority": defaults["priority"],
        cf["change_type"]: config.resolve_tckt_select(
            "change_type", ss.get("stk_change_type", "Normal"),
        ),
        cf["change_risk"]: config.resolve_tckt_select(
            "change_risk", ss.get("stk_change_risk", "Medium"),
        ),
        cf["planned_start"]: start_iso,
        cf["planned_end"]: end_iso,
        impl_key: impl_adf,
        test_key: test_adf,
        backout_key: backout_adf,
        cf["business_impact"]: impact_adf,
    }
    impact_val = str(ss.get("stk_impact") or "").strip()
    urgency_val = str(ss.get("stk_urgency") or "").strip()
    if impact_val and cf.get("impact"):
        fields[cf["impact"]] = config.resolve_tckt_select("impact", impact_val)
    if urgency_val and cf.get("urgency"):
        fields[cf["urgency"]] = config.resolve_tckt_select("urgency", urgency_val)
    if not is_test and defaults.get("affected_services") and cf.get("affected_services"):
        fields[cf["affected_services"]] = defaults["affected_services"]
    if cf.get("communication_plan"):
        fields[cf["communication_plan"]] = comm_adf
    if cf.get("reason_for_change") and reason_text:
        fields[cf["reason_for_change"]] = reason_text
    risks_text = str(ss.get("stk_risks_management") or "").strip()
    qa_text = str(ss.get("stk_qa_test_plan") or "").strip()
    risks_key = cf.get("risks_management", "")
    qa_key = cf.get("qa_test_plan", "")
    if risks_key and risks_text:
        fields[risks_key] = _multi_para_adf(risks_text)
    if qa_key and qa_text:
        fields[qa_key] = _text_to_adf(qa_text)
    if cf.get("unplanned") and defaults.get("unplanned"):
        fields[cf["unplanned"]] = defaults["unplanned"]
    if not is_test and cf.get("assignment_group") and assignment_group:
        fields[cf["assignment_group"]] = assignment_group
    if not is_test and cf.get("team") and team_value:
        fields[cf["team"]] = team_value
    if not is_test:
        if cf.get("approvers") and approvers:
            fields[cf["approvers"]] = approvers
        if approver_groups and cf.get("approver_groups"):
            fields[cf["approver_groups"]] = approver_groups
    if cf.get("affects_pf") and defaults.get("affects_pf"):
        fields[cf["affects_pf"]] = defaults["affects_pf"]
    if cf.get("outage_required") and defaults.get("outage_required"):
        fields[cf["outage_required"]] = defaults["outage_required"]

    issue_key = ""
    post_create_error: str | None = None
    create_error: dict | None = None

    with st.spinner("Creating SHIPIT service ticket\u2026"):
        try:
            result, rt_status = jira_client.create_tckt_issue(summary, fields)
            issue_key = result.get("key", "")
            if not issue_key:
                raise jira_client.JiraApiError(
                    f"Jira returned a response without a ticket key: {result!r}"
                )

            ss["stk_created_key"] = issue_key
            ss["stk_created_url"] = f"{config.JIRA_BASE_URL}/browse/{issue_key}"
            ss["_stk_just_created"] = True
            ss.pop("_stk_create_error", None)
            from session_persist import persist_session

            persist_session(dict(ss))
            post_create_error = result.get("supplementalWarning")

            try:
                ss["stk_rt_status"] = rt_status
                ss["stk_rt_auto_set"] = rt_status.ok
                ss["stk_assignment_warnings"] = _verify_assignments(
                    issue_key,
                    approvers,
                    approver_groups,
                    expected_team=team_value,
                    expected_assignment_group=assignment_group,
                )
                window = _schedule_window(ss)
                if window:
                    try:
                        jira_client.add_schedule_window_comment(issue_key, window)
                        ss["stk_schedule_comment_ok"] = True
                        ss.pop("stk_schedule_comment_error", None)
                    except Exception as comment_exc:
                        logger.warning(
                            "Schedule window comment failed for %s: %s",
                            issue_key, comment_exc,
                        )
                        ss["stk_schedule_comment_ok"] = False
                        ss["stk_schedule_comment_error"] = str(comment_exc)
            except Exception as post_exc:
                logger.debug("TCKT post-create steps failed", exc_info=True)
                post_create_error = str(post_exc)
                warnings = list(ss.get("stk_assignment_warnings") or [])
                warnings.append(f"Post-create setup incomplete: {post_exc}")
                ss["stk_assignment_warnings"] = warnings

            started = ss.get("stk_draft_started_at")
            if started:
                release_stats.record_draft_timing(
                    ss, time.time() - float(started),
                )

        except Exception as exc:
            if ss.get("stk_created_key"):
                ss["_stk_just_created"] = True
                post_create_error = str(exc)
            else:
                logger.error("TCKT creation failed", exc_info=True)
                create_error = _describe_create_failure(exc)
                create_error["existing"] = _find_existing_after_failure(summary)
        finally:
            ss.pop("_stk_creating", None)

    if create_error:
        ss["_stk_create_error"] = create_error
    if post_create_error:
        ss["_stk_post_create_warning"] = post_create_error

    st.rerun()
