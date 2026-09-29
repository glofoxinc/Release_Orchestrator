"""Step 2 — Fill in TCKT ticket details with smart defaults."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

import config
import release_defaults
import schedule_time
import shipit_test_mode
import shipit_reference
from release_platform.ui.helpers import (
    esc,
    release_notes_doc_filename,
    ss_default,
    sync_sharepoint_from_shared,
    sync_stk_release_defaults,
)
from release_platform.ui.workflow import is_service_ticket_standalone, render_action_hint, save_sharepoint_url, validate_sharepoint_url


def _go(step: int) -> None:
    from release_platform.ui.service_ticket.nav import go_step

    go_step(step)


def _approvers_to_text(approvers: list[dict]) -> str:
    lines: list[str] = []
    for item in approvers or []:
        if not isinstance(item, dict):
            continue
        account_id = item.get("accountId") or item.get("account_id") or ""
        name = item.get("displayName") or item.get("name") or ""
        if account_id and name:
            lines.append(f"{account_id}  # {name}")
        elif account_id:
            lines.append(str(account_id))
    return "\n".join(lines)


def _groups_to_text(groups: list[dict]) -> str:
    lines: list[str] = []
    for item in groups or []:
        if isinstance(item, dict):
            name = item.get("name") or ""
        else:
            name = str(item)
        if name:
            lines.append(name)
    return "\n".join(lines)


def _parse_approvers_text(raw: str) -> list[dict]:
    out: list[dict] = []
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append({"accountId": line})
    return out


def _parse_groups_text(raw: str) -> list[dict]:
    return [{"name": line.strip()} for line in raw.splitlines() if line.strip()]


def _sync_approver_defaults() -> None:
    ss_default("stk_approvers", list(config.TCKT_DEFAULTS.get("approvers", [])))
    ss_default("stk_approver_groups", list(config.TCKT_DEFAULTS.get("approver_groups", [])))


def _render_shipit_reference_panel() -> None:
    """Load schedule, approver groups, and classification from a production SHIPIT ticket."""
    st.markdown("### Start from reference ticket")
    st.caption(
        f"Gold standards: **[SHIPIT-17036](https://abcfinancial.atlassian.net/browse/SHIPIT-17036)** (Analyze) and "
        f"**[SHIPIT-17191](https://abcfinancial.atlassian.net/browse/SHIPIT-17191)** (multi-custom PIC). Default template: "
        f"**[{shipit_reference.DEFAULT_REFERENCE_KEY}](https://abcfinancial.atlassian.net/browse/{shipit_reference.DEFAULT_REFERENCE_KEY})** "
        "as the template — **10:30 AM–11:30 AM IST** (shown as US Central in Jira), "
        "**Insights Customize Approvers** group, and normal change classification."
    )

    ref_key = st.session_state.get("stk_reference_key", "")
    if ref_key:
        st.success(f"Reference loaded: **{esc(ref_key)}**")

    try:
        recent = shipit_reference.search_deployment_tickets(max_results=15)
    except Exception as exc:
        st.warning(f"Could not fetch recent SHIPIT tickets: {exc}")
        recent = []

    group_options = shipit_reference.collect_approver_group_options(recent)

    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    with c1:
        if st.button(
            f"Apply {shipit_reference.DEFAULT_REFERENCE_KEY} template",
            type="primary",
            key="stk_apply_default_ref",
            use_container_width=True,
        ):
            try:
                ref = shipit_reference.apply_shipit_template(st.session_state)
                st.session_state["stk_approver_groups"] = list(ref.approver_groups) or [
                    {"name": n} for n in group_options
                ]
                st.success(
                    f"Applied schedule ({ref.planned_start_time}–{ref.planned_end_time} "
                    f"{ref.schedule_timezone or config.TCKT_SCHEDULE_TZ}) and approver groups."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load template: {exc}")
    with c2:
        manual_key = st.text_input(
            "Other SHIPIT key",
            value="",
            placeholder=shipit_reference.DEFAULT_REFERENCE_KEY,
            key="_stk_ref_manual",
        )
        if st.button("Load ticket", key="stk_load_ref", disabled=not manual_key.strip()):
            try:
                ref = shipit_reference.apply_shipit_template(
                    st.session_state,
                    issue_key=manual_key.strip(),
                    include_summary=st.session_state.get("_stk_ref_summary", False),
                )
                st.success(f"Loaded {ref.key}.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load {manual_key.strip().upper()}: {exc}")
    with c3:
        st.checkbox("Replace summary too", value=False, key="_stk_ref_summary")

    if recent:
        options = [t.get("key", "") for t in recent if t.get("key")]
        picked = st.selectbox(
            "Recent production SHIPIT tickets",
            options or list(shipit_reference.GOLD_STANDARD_KEYS),
            format_func=lambda k: next(
                (
                    f"{k} — {(t.get('fields', {}).get('summary') or '')[:70]}"
                    for t in recent
                    if t.get("key") == k
                ),
                k,
            ),
            key="_stk_ref_pick",
        )
        if st.button("Load selected ticket", key="stk_load_picked", use_container_width=True):
            try:
                shipit_reference.apply_shipit_template(
                    st.session_state,
                    issue_key=picked,
                    include_summary=st.session_state.get("_stk_ref_summary", False),
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load {picked}: {exc}")

    if group_options:
        st.caption(f"Known approver groups: {', '.join(group_options)}")


def _sync_routing_defaults() -> None:
    defaults = config.TCKT_DEFAULTS
    ss_default("stk_assignment_group", dict(defaults.get("assignment_group", {}) or {}))
    ss_default("stk_team", str(defaults.get("team", "") or ""))


def _render_routing_section() -> None:
    _sync_routing_defaults()
    st.markdown("### Assignment Group & Team")
    st.caption(
        "Set before creation — written to Jira when the TCKT is created "
        "(not applied after the fact)."
    )

    ag = st.session_state.get("stk_assignment_group") or {}
    ag_label = config.TCKT_DEFAULTS.get("assignment_group_name", "")
    st.text_input(
        "Assignment Group",
        value=ag_label or str(ag.get("value") or ag.get("id") or ""),
        disabled=True,
        key="_stk_assignment_group_display",
        help="Configured in workspace.yaml (service_desk.defaults.assignment_group).",
    )

    team_name = config.TCKT_DEFAULTS.get("team_name", "")
    team_id = st.session_state.get("stk_team", "")
    st.text_input(
        "Team",
        value=team_name or team_id,
        disabled=True,
        key="_stk_team_display",
        help="Configured in workspace.yaml (service_desk.defaults.team).",
    )


def _render_approvers_section(group_options: list[str] | None = None) -> None:
    _sync_approver_defaults()
    st.markdown("### Approvers & Groups")
    st.caption(
        "SHIPIT-17036 uses **approver groups only** (no named approvers). "
        "Pick groups below — validated against Jira before create."
    )

    options = list(group_options or [])
    for item in st.session_state.get("stk_approver_groups") or []:
        name = item.get("name") if isinstance(item, dict) else str(item)
        if name and name not in options:
            options.append(name)
    options = sorted(set(options))

    current_names = [
        (g.get("name") if isinstance(g, dict) else str(g))
        for g in (st.session_state.get("stk_approver_groups") or [])
    ]
    current_names = [n for n in current_names if n]

    if options:
        if "_stk_group_multiselect" not in st.session_state:
            st.session_state["_stk_group_multiselect"] = [
                n for n in current_names if n in options
            ]
        picked = st.multiselect(
            "Approver groups",
            options=options,
            key="_stk_group_multiselect",
            help="Select one or more Jira groups. Default matches SHIPIT-17036.",
        )
        st.session_state["stk_approver_groups"] = [{"name": n} for n in picked]

    with st.expander("Advanced: edit approvers / groups as text", expanded=not bool(options)):
        st.session_state["stk_approvers"] = _parse_approvers_text(st.text_area(
            "Approvers (one accountId per line — optional)",
            value=_approvers_to_text(st.session_state.get("stk_approvers", [])),
            height=80,
            key="_stk_approvers_text",
        ))
        if not options:
            st.session_state["stk_approver_groups"] = _parse_groups_text(st.text_area(
                "Approver groups (one name per line)",
                value=_groups_to_text(st.session_state.get("stk_approver_groups", [])),
                height=80,
                key="_stk_groups_text",
            ))

    if st.button("Validate approvers & groups", key="stk_validate_assignments"):
        import approver_validator

        cache = st.session_state.setdefault("_approver_validation_cache", {})
        result = approver_validator.validate_defaults(
            st.session_state.get("stk_approvers", []),
            st.session_state.get("stk_approver_groups", []),
            cache=cache,
        )
        st.session_state["stk_approver_validation"] = result
        st.rerun()

    result = st.session_state.get("stk_approver_validation")
    if result is not None:
        if result.all_ok:
            st.success("All approvers and groups are valid in Jira.")
        else:
            st.error("Fix assignment issues before creating the TCKT:")
            for msg in result.failures:
                st.markdown(f"- {esc(msg)}")


def _apply_deployment_profile(ss, profile_key: str) -> None:
    profiles = release_defaults.deployment_profiles()
    profile = profiles.get(profile_key) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        return
    if profile.get("change_type"):
        ss["stk_change_type"] = str(profile["change_type"])
    sched = profile.get("schedule") or {}
    if isinstance(sched, dict):
        from datetime import datetime as dt

        if sched.get("start_time"):
            try:
                ss["stk_planned_start_time"] = dt.strptime(
                    str(sched["start_time"]), "%H:%M"
                ).time()
            except ValueError:
                pass
        if sched.get("end_time"):
            try:
                ss["stk_planned_end_time"] = dt.strptime(
                    str(sched["end_time"]), "%H:%M"
                ).time()
            except ValueError:
                pass
        if sched.get("source_timezone"):
            ss["stk_schedule_tz"] = str(sched["source_timezone"])


def _render_test_shipit_tools(ss) -> None:
    """MCP parity: explicit test SHIPIT mode (no approvers, safe to dispose)."""
    with st.expander("Test SHIPIT mode (DO NOT DEPLOY)", expanded=False):
        st.caption(
            "Matches MCP **test shipit**. Creates a demo change ticket without approver groups "
            "or affected services. Use **Dispose test ticket** on Step 6 after validation."
        )
        test_on = st.checkbox(
            "Create as TEST SHIPIT (demo / migration validation only)",
            value=bool(ss.get("stk_test_mode")),
            key="_stk_test_mode_cb",
        )
        ss["stk_test_mode"] = test_on
        if test_on:
            version_hint = str(ss.get("rn_version") or ss.get("stk_summary") or "").lstrip("v")
            if version_hint:
                ss["stk_summary"] = shipit_test_mode.default_test_summary(version_hint)
            st.info(f"Summary will use: **{esc(ss.get('stk_summary', ''))}**")


def _render_deployment_profile_tools(ss) -> None:
    profiles = release_defaults.deployment_profiles()
    last = release_defaults.load_last_schedule_window()
    cols = st.columns([1, 1, 2])
    if profiles:
        keys = list(profiles.keys())
        with cols[0]:
            choice = st.selectbox(
                "Deployment profile",
                keys,
                format_func=lambda k: str((profiles.get(k) or {}).get("label") or k),
                key="_stk_deploy_profile_pick",
            )
            if st.button("Apply profile", key="_stk_apply_profile", use_container_width=True):
                _apply_deployment_profile(ss, choice)
                st.rerun()
    with cols[1]:
        if last and st.button("Use last window", key="_stk_last_window", use_container_width=True):
            ss["stk_planned_start_date"] = last["start_date"]
            ss["stk_planned_start_time"] = last["start_time"]
            ss["stk_planned_end_date"] = last["end_date"]
            ss["stk_planned_end_time"] = last["end_time"]
            ss["stk_schedule_tz"] = last["timezone_name"]
            st.rerun()


def _ensure_schedule_fields(ss) -> None:
    """Default missing planned window fields (10:30–11:30 AM IST)."""
    from datetime import datetime

    import release_defaults as rd

    sched = rd.default_deployment_schedule()
    ss_default("stk_schedule_tz", sched["source_timezone"])
    if ss.get("stk_planned_start_date") is None:
        ss["stk_planned_start_date"] = datetime.now().date()
    if ss.get("stk_planned_start_time") is None:
        ss["stk_planned_start_time"] = sched["start_time"]
    if ss.get("stk_planned_end_date") is None:
        ss["stk_planned_end_date"] = ss["stk_planned_start_date"]
    if ss.get("stk_planned_end_time") is None:
        ss["stk_planned_end_time"] = sched["end_time"]


def _render_schedule(ss) -> None:
    """Planned window inputs plus how Jira will render them for reviewers."""
    _ensure_schedule_fields(ss)
    ss_default("stk_schedule_tz", config.TCKT_SCHEDULE_SOURCE_TZ)

    tz_options = list(schedule_time.COMMON_TIMEZONES)
    current_tz = ss.get("stk_schedule_tz") or config.TCKT_SCHEDULE_SOURCE_TZ
    if current_tz not in tz_options:
        tz_options.insert(0, current_tz)

    c1, c2, c3 = st.columns([1, 1, 1.2])
    with c1:
        ss["stk_planned_start_date"] = st.date_input(
            "Planned Start Date",
            value=ss["stk_planned_start_date"],
            key="_stk_psd",
            help="Deployment window open date. Auto-set from the release version name.",
        )
        ss["stk_planned_start_time"] = st.time_input(
            "Planned Start Time",
            value=ss["stk_planned_start_time"],
            key="_stk_pst",
            help="Deployment window open time (default 10:30 AM IST).",
        )
    with c2:
        ss["stk_planned_end_date"] = st.date_input(
            "Planned End Date",
            value=ss["stk_planned_end_date"],
            key="_stk_ped",
            help="Deployment window close date.",
        )
        ss["stk_planned_end_time"] = st.time_input(
            "Planned End Time",
            value=ss["stk_planned_end_time"],
            key="_stk_pet",
            help="Deployment window close time (default 11:30 AM IST).",
        )
    with c3:
        ss["stk_schedule_tz"] = st.selectbox(
            "Times are in",
            tz_options,
            index=tz_options.index(current_tz),
            format_func=schedule_time.zone_label,
            key="_stk_sched_tz",
            help=(
                "The timezone you are entering the window in. Jira stores the "
                "instant and shows each viewer their own timezone."
            ),
        )

    render_schedule_timezone_preview(ss)


def render_schedule_timezone_preview(ss) -> None:
    """Show the entered window next to what Jira reviewers will see."""
    start_d = ss.get("stk_planned_start_date")
    start_t = ss.get("stk_planned_start_time")
    end_d = ss.get("stk_planned_end_date")
    end_t = ss.get("stk_planned_end_time")
    if not (start_d and start_t and end_d and end_t):
        return

    info = schedule_time.describe_window(
        start_d,
        start_t,
        end_d,
        end_t,
        tz_name=ss.get("stk_schedule_tz") or config.TCKT_SCHEDULE_SOURCE_TZ,
        display_tz=config.TCKT_DISPLAY_TZ,
    )

    if not info["valid"]:
        st.error("Planned end is before or equal to planned start.")
        return

    duration = schedule_time.duration_label(int(info["duration_minutes"]))
    st.markdown(
        f"**You entered:** {esc(str(info['entered_start']))} \u2192 "
        f"{esc(str(info['entered_end']))}  ({esc(duration)})"
    )

    if info["same_zone"]:
        return

    st.markdown(
        f"**Jira will show approvers:** {esc(str(info['display_start']))} \u2192 "
        f"{esc(str(info['display_end']))}"
    )
    if info["display_crosses_day"]:
        st.info(
            "Approvers read this ticket in "
            f"{esc(str(info['display_timezone']))}, where the window falls on the "
            "previous night and looks like an overnight change. The instant is "
            "correct \u2014 mention the local time in the plans, or switch "
            "**Times are in** to the reviewer timezone if the window was agreed "
            "in their clock."
        )
    else:
        st.caption(
            f"Same instant, shown in {esc(str(info['display_timezone']))} "
            "\u2014 this is what Command Center and approvers will read."
        )


def render() -> None:
    st.markdown("## Ticket Details")
    st.markdown(
        "Configure the SHIPIT change ticket. "
        "**Paste your Release Notes SharePoint link** below when you have it — "
        "that link is embedded in the description sent to approvers."
    )

    sync_stk_release_defaults()
    sync_sharepoint_from_shared()

    try:
        _recent_shipit = shipit_reference.search_deployment_tickets(max_results=15)
    except Exception:
        _recent_shipit = []
    _group_options = shipit_reference.collect_approver_group_options(_recent_shipit)

    _render_shipit_reference_panel()

    st.markdown("### Summary")
    st.session_state["stk_summary"] = st.text_input(
        "Ticket Summary",
        value=st.session_state["stk_summary"],
        key="_stk_summary",
        help="The Jira issue summary line. Auto-generated to match SHIPIT production format.",
    )

    st.markdown("### Schedule")
    st.caption(
        "Enter the deployment window in **IST (10:30–11:30 AM)** — the same instant "
        "is stored in Jira as **US Central (CST/CDT)** for Command Center approvers. "
        "Dates default from the release version."
    )
    _render_deployment_profile_tools(st.session_state)
    _render_test_shipit_tools(st.session_state)
    _render_schedule(st.session_state)

    with st.expander("Advanced Options", expanded=False):
        st.markdown("#### Classification & Risk")
        st.caption(
            "Defaults are pre-filled for normal deployments. "
            "Override only for emergencies or high-risk changes."
        )
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            ss_default("stk_change_type", "Normal")
            st.session_state["stk_change_type"] = st.selectbox(
                "Change Type",
                ["Normal", "Emergency"],
                index=0 if st.session_state["stk_change_type"] == "Normal" else 1,
                key="_stk_ct",
                help="Normal for scheduled deployments, Emergency for hotfixes.",
            )
        with c2:
            ss_default("stk_change_risk", "Medium")
            risk_opts = ["Low", "Medium", "High"]
            risk_val = st.session_state.get("stk_change_risk", "Medium")
            risk_idx = risk_opts.index(risk_val) if risk_val in risk_opts else 1
            st.session_state["stk_change_risk"] = st.selectbox(
                "Change Risk",
                risk_opts,
                index=risk_idx,
                key="_stk_cr",
                help="Risk level based on deployment scope and complexity.",
            )
        with c3:
            ss_default("stk_impact", "")
            impact_opts = [
                "Not set",
                "Moderate / Limited",
                "Extensive / Widespread",
                "Significant / Large",
            ]
            impact_val = st.session_state.get("stk_impact", "")
            impact_idx = (
                impact_opts.index(impact_val)
                if impact_val in impact_opts
                else 0
            )
            picked = st.selectbox(
                "Impact",
                impact_opts,
                index=impact_idx,
                key="_stk_imp",
                help="Leave as Not set for standard Glofox prod SHIPIT (Rekha pattern).",
            )
            st.session_state["stk_impact"] = "" if picked == "Not set" else picked
        with c4:
            ss_default("stk_urgency", "")
            urgency_opts = ["Not set", "Low", "Medium", "High"]
            urgency_val = st.session_state.get("stk_urgency", "")
            urgency_idx = (
                urgency_opts.index(urgency_val)
                if urgency_val in urgency_opts
                else 0
            )
            picked = st.selectbox(
                "Urgency",
                urgency_opts,
                index=urgency_idx,
                key="_stk_urg",
                help="Leave as Not set for standard Glofox prod SHIPIT (Rekha pattern).",
            )
            st.session_state["stk_urgency"] = "" if picked == "Not set" else picked

    st.markdown("### SharePoint link (required)")
    standalone = is_service_ticket_standalone()
    st.info(
        "**You provide the link** after uploading `Release Notes YYYY.M.MM.DD.docx` to SharePoint. "
        "Paste the document URL here — it becomes a clickable link in the SHIPIT description."
    )
    if standalone:
        st.caption(
            "Quick start: generate the .docx in Release Notes (or upload your own), "
            "then paste the SharePoint sharing URL here."
        )
    else:
        st.caption(
            "Complete Release Notes Step 4 first, or paste the link if you uploaded manually."
        )
    shared_sp = st.session_state.get("shared_sharepoint_url", "")
    ss_default("stk_sharepoint", shared_sp)
    expected_label = release_notes_doc_filename("stk_" if standalone else "rn_")
    if shared_sp:
        st.caption(
            f"TCKT description link text will be **{expected_label}** "
            f"(must point to that uploaded file)."
        )
    if shared_sp and st.session_state["stk_sharepoint"] == shared_sp:
        docx_name = st.session_state.get("shared_docx_filename", "")
        hint = f" (from Release Notes: {docx_name})" if docx_name else " (from Release Notes step)"
        st.caption(f"Pre-filled{hint}")
    st.session_state["stk_sharepoint"] = st.text_input(
        "Release Notes SharePoint URL",
        value=st.session_state["stk_sharepoint"],
        placeholder="https://yourorg.sharepoint.com/...",
        key="_stk_sp",
        help="Required. Service Ticket cannot proceed without this link.",
    )
    if st.session_state["stk_sharepoint"]:
        save_sharepoint_url(st.session_state["stk_sharepoint"], source="stk")
    if st.session_state["stk_sharepoint"] and not validate_sharepoint_url(st.session_state["stk_sharepoint"]):
        from sharepoint_url import sharepoint_validation_message

        st.error(
            sharepoint_validation_message(st.session_state["stk_sharepoint"])
            or "Enter a valid SharePoint (*.sharepoint.com) document URL."
        )

    sp_ok = validate_sharepoint_url(st.session_state.get("stk_sharepoint", ""))
    doc_ok = bool(st.session_state.get("shared_docx_generated"))
    if not standalone and not doc_ok:
        st.warning("Release Notes `.docx` has not been generated yet. Complete Release Notes Step 4 first.")

    _render_routing_section()
    _render_approvers_section(_group_options)

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Back", key="stk_s2_back"):
            _go(1)
    with c2:
        can_continue = sp_ok and bool(st.session_state.get("stk_summary", "").strip())
        if not standalone:
            can_continue = can_continue and doc_ok
        if st.button("Build Description \u2192", type="primary", key="stk_s2_next", disabled=not can_continue):
            ss = st.session_state
            sd = ss.get("stk_planned_start_date")
            st_t = ss.get("stk_planned_start_time")
            ed = ss.get("stk_planned_end_date")
            et = ss.get("stk_planned_end_time")
            if sd and st_t and ed and et:
                release_defaults.save_last_schedule_window(
                    start_date=sd,
                    start_time=st_t,
                    end_date=ed,
                    end_time=et,
                    timezone_name=str(ss.get("stk_schedule_tz") or config.TCKT_SCHEDULE_TZ),
                )
            _go(3)
        if not can_continue:
            if standalone:
                render_action_hint("Needs: summary and a valid SharePoint link to your Release Notes file.")
            else:
                render_action_hint(
                    "Needs: summary, generated Release Notes doc, and valid SharePoint link."
                )
        else:
            render_action_hint(
                "Builds the Jira description from your tickets and SharePoint link."
            )
