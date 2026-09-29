"""Reusable Streamlit panel for Teams review and deployment meetings."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

import streamlit as st

import config
import teams_schedule
from teams_meeting_content import (
    MeetingContext,
    attendees_for_groups,
    attendees_to_text,
    build_meeting_body,
    collect_assignee_attendees,
    collect_release_owner_attendee,
    default_meeting_window,
    default_subject,
    load_attendee_groups,
    merge_attendees,
    parse_attendees_text,
    template_attendee_groups,
)


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _as_time(value: time | datetime) -> time:
    return value.time() if isinstance(value, datetime) else value


def _render_readiness(cfg: teams_schedule.TeamsScheduleConfig) -> None:
    steps = teams_schedule.readiness_steps(cfg)
    pending = [s for s in steps if not s.get("ok")]
    if cfg.can_schedule():
        st.success("Teams scheduling is **live-ready**. Preview, then click **Schedule in Teams**.")
    elif pending:
        st.info(
            f"**{len(pending)} setup step(s) remaining** for live scheduling. "
            "Preview works now; add MS_GRAPH_* to `.env` to go live."
        )
    for step in steps:
        icon = "✅" if step.get("ok") else "⬜"
        line = f"{icon} **{step.get('label', step.get('id', '?'))}** — {step.get('detail', '')}"
        if not step.get("ok") and step.get("fix"):
            line += f"  \n*Fix:* {step['fix']}"
        st.markdown(line)


def _render_saved_meeting(kind: str) -> None:
    join_key = f"shared_teams_{kind}_url"
    web_key = f"shared_teams_{kind}_web"
    event_key = f"shared_teams_{kind}_event_id"
    join_url = str(st.session_state.get(join_key) or "").strip()
    web_url = str(st.session_state.get(web_key) or "").strip()
    event_id = str(st.session_state.get(event_key) or "").strip()
    if not join_url and not web_url and not event_id:
        return
    st.markdown("**Scheduled meeting**")
    if join_url:
        st.link_button("Open Teams join link", join_url, use_container_width=False)
        st.code(join_url, language=None)
    if web_url:
        st.caption(f"[Outlook calendar event]({web_url})")
    if event_id:
        st.caption("Event ID saved — use **Update scheduled meeting** below to reschedule.")


def _init_session_defaults(
    *,
    prefix: str,
    kind: str,
    version: str,
    cfg: teams_schedule.TeamsScheduleConfig,
    meeting_context: MeetingContext | None,
    default_start: datetime | None = None,
    default_end: datetime | None = None,
) -> None:
    """Auto-fill subject/body/attendees once per version (user can edit afterward)."""
    init_key = f"_{prefix}_init_version"
    if st.session_state.get(init_key) == version:
        return

    ctx = meeting_context or MeetingContext(version=version, kind=kind)
    ctx.version = version
    ctx.kind = kind

    st.session_state[f"_{prefix}_subject"] = default_subject(kind, version)
    st.session_state[f"_{prefix}_body"] = build_meeting_body(ctx)
    base_people = cfg.attendees_for_kind(kind)  # type: ignore[arg-type]
    assignees = collect_assignee_attendees(ctx.tickets or [])
    if ctx.grouped:
        grouped_tickets = [iss for group in ctx.grouped.values() for iss in group]
        assignees = collect_assignee_attendees(grouped_tickets)
    group_people = attendees_for_groups(template_attendee_groups(kind))
    st.session_state[f"_{prefix}_attendees"] = attendees_to_text(
        merge_attendees(base_people, group_people, assignees)
    )
    deploy_date = None
    if meeting_context and meeting_context.deploy_date:
        deploy_date = meeting_context.deploy_date
    slot_start, slot_end = default_meeting_window(
        kind,
        deploy_date=deploy_date,
        deploy_start=default_start if kind == "deployment" else None,
        deploy_end=default_end if kind == "deployment" else None,
    )
    st.session_state[f"_{prefix}_start_date"] = slot_start.date()
    st.session_state[f"_{prefix}_start_time"] = slot_start.time().replace(second=0, microsecond=0)
    st.session_state[f"_{prefix}_end_date"] = slot_end.date()
    st.session_state[f"_{prefix}_end_time"] = slot_end.time().replace(second=0, microsecond=0)
    st.session_state[init_key] = version


def _render_attendee_tools(
    *,
    prefix: str,
    cfg: teams_schedule.TeamsScheduleConfig,
    kind: str,
    meeting_context: MeetingContext | None,
) -> None:
    ctx = meeting_context or MeetingContext(kind=kind)
    tickets = list(ctx.tickets or [])
    if ctx.grouped:
        tickets = [iss for group in ctx.grouped.values() for iss in group]

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        if st.button("Reset roster", key=f"{prefix}_att_reset", use_container_width=True):
            st.session_state[f"_{prefix}_attendees"] = attendees_to_text(
                merge_attendees(
                    cfg.attendees_for_kind(kind),  # type: ignore[arg-type]
                    attendees_for_groups(template_attendee_groups(kind)),
                )
            )
            st.rerun()
    with c2:
        if st.button("+ Assignees", key=f"{prefix}_att_assignees", use_container_width=True):
            current = parse_attendees_text(st.session_state.get(f"_{prefix}_attendees", ""))
            merged = merge_attendees(current, collect_assignee_attendees(tickets))
            st.session_state[f"_{prefix}_attendees"] = attendees_to_text(merged)
            st.rerun()
    with c3:
        if st.button("+ Core team", key=f"{prefix}_att_core", use_container_width=True):
            current = parse_attendees_text(st.session_state.get(f"_{prefix}_attendees", ""))
            merged = merge_attendees(current, cfg.default_attendees)
            st.session_state[f"_{prefix}_attendees"] = attendees_to_text(merged)
            st.rerun()
    with c4:
        if st.button("Regenerate body", key=f"{prefix}_body_regen", use_container_width=True):
            body_ctx = MeetingContext(
                version=ctx.version,
                kind=kind,
                base_url=ctx.base_url,
                tickets=tickets,
                grouped=ctx.grouped,
                sharepoint_url=ctx.sharepoint_url,
                tckt_key=ctx.tckt_key,
                tckt_url=ctx.tckt_url,
                deploy_window=ctx.deploy_window,
                blocked_tickets=ctx.blocked_tickets,
                team_name=ctx.team_name,
            )
            st.session_state[f"_{prefix}_body"] = build_meeting_body(body_ctx)
            st.rerun()
    groups = load_attendee_groups()
    with c5:
        if groups and st.button("+ Groups", key=f"{prefix}_att_groups", use_container_width=True):
            current = parse_attendees_text(st.session_state.get(f"_{prefix}_attendees", ""))
            merged = merge_attendees(current, attendees_for_groups(template_attendee_groups(kind)))
            st.session_state[f"_{prefix}_attendees"] = attendees_to_text(merged)
            st.rerun()
    with c6:
        if st.button("+ Owner", key=f"{prefix}_att_owner", use_container_width=True):
            current = parse_attendees_text(st.session_state.get(f"_{prefix}_attendees", ""))
            owner_people = [p for p in collect_release_owner_attendee() if p.email]
            if owner_people:
                merged = merge_attendees(current, owner_people)
                st.session_state[f"_{prefix}_attendees"] = attendees_to_text(merged)
                st.rerun()
            else:
                st.caption("Set release_owner in workspace release_notes.")


def _schedule_one(
    *,
    prefix: str,
    kind: teams_schedule.MeetingKind,
    cfg: teams_schedule.TeamsScheduleConfig,
    draft: teams_schedule.MeetingDraft,
    dry_run: bool,
    update_event_id: str = "",
) -> None:
    if update_event_id:
        result = teams_schedule.update_meeting(
            cfg, update_event_id, draft, dry_run=dry_run
        )
    else:
        result = teams_schedule.schedule_meeting(cfg, draft, dry_run=dry_run)
    st.session_state[f"{prefix}_result"] = result.to_dict()
    if result.ok and not dry_run:
        if result.event_id:
            st.session_state[f"shared_teams_{kind}_event_id"] = result.event_id
        if result.join_url:
            st.session_state[f"shared_teams_{kind}_url"] = result.join_url
        if result.web_link:
            st.session_state[f"shared_teams_{kind}_web"] = result.web_link
        from session_persist import persist_session

        persist_session(dict(st.session_state), notify=True)


def _render_schedule_result(prefix: str, *, subject: str) -> None:
    result = st.session_state.get(f"{prefix}_result")
    if not isinstance(result, dict):
        return
    if result.get("ok") and result.get("dry_run"):
        draft_data = result.get("draft") or {}
        attendee_count = len((draft_data.get("attendees") or []))
        action = "Update preview ready" if result.get("updated") else "Preview ready"
        st.success(
            f"{action}: "
            f"**{draft_data.get('subject', subject)}**, "
            f"{draft_data.get('start', '')} -> {draft_data.get('end', '')} "
            f"({attendee_count} attendee(s))."
        )
        with st.expander("Graph payload (debug)", expanded=False):
            payload = result.get("graph_payload") or {}
            st.code(json.dumps(payload, indent=2), language="json")
    elif result.get("ok"):
        join_url = result.get("join_url") or ""
        updated = result.get("updated") is True
        st.success("Teams meeting updated." if updated else "Teams meeting scheduled.")
        if join_url:
            st.link_button("Open Teams meeting", join_url)
            st.code(join_url, language=None)
        web_link = result.get("web_link") or ""
        if web_link:
            st.link_button("Open in Outlook", web_link)
    else:
        st.error(result.get("error") or "Teams scheduling failed.")


def render_teams_schedule_panel(
    *,
    kind: teams_schedule.MeetingKind,
    version: str = "",
    default_start: datetime | None = None,
    default_end: datetime | None = None,
    timezone_name: str | None = None,
    meeting_context: MeetingContext | None = None,
) -> None:
    """Render preview/live Teams scheduling using the shared Graph backend."""
    if kind not in {"review", "deployment"}:
        raise ValueError(f"Unsupported Teams meeting kind: {kind}")

    cfg = teams_schedule.load_schedule_config(config.TEAMS_SCHEDULE)
    prefix = f"teams_{kind}"
    label = "review call" if kind == "review" else "deployment call"

    ctx = meeting_context or MeetingContext(version=version, kind=kind)
    ctx.version = version or ctx.version
    ctx.kind = kind
    _init_session_defaults(
        prefix=prefix,
        kind=kind,
        version=version,
        cfg=cfg,
        meeting_context=ctx,
        default_start=default_start,
        default_end=default_end,
    )

    start = default_start
    end = default_end
    if start is None or end is None:
        slot_start, slot_end = default_meeting_window(
            kind,
            deploy_start=default_start if kind == "deployment" else None,
            deploy_end=default_end if kind == "deployment" else None,
        )
        start = start or slot_start
        end = end or slot_end
    start = start or datetime.now().replace(second=0, microsecond=0) + timedelta(hours=1)
    duration = (
        cfg.review_duration_minutes
        if kind == "review"
        else cfg.deployment_duration_minutes
    )
    end = end or (start + timedelta(minutes=duration))

    with st.expander(f"Schedule Teams {label}", expanded=cfg.can_schedule() is False):
        _render_readiness(cfg)
        _render_saved_meeting(kind)

        if kind == "deployment" and default_start and default_end:
            st.caption(
                "Times pre-filled from your TCKT deployment window above. "
                "Adjust if the Teams call should differ from the change window."
            )

        subject = st.text_input(
            "Meeting subject",
            value=st.session_state.get(f"_{prefix}_subject", default_subject(kind, version)),
            key=f"_{prefix}_subject",
        )
        meeting_body = st.text_area(
            "Meeting body (HTML in invite)",
            value=st.session_state.get(f"_{prefix}_body", ""),
            key=f"_{prefix}_body",
            height=160,
            help="Auto-filled with tickets / SharePoint link. Use Regenerate body to refresh.",
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            init_start = st.session_state.get(f"_{prefix}_start_date", start.date())
            init_start_time = st.session_state.get(f"_{prefix}_start_time", start.time())
            start_date = st.date_input(
                "Start date",
                value=init_start,
                key=f"_{prefix}_start_date",
            )
            start_time = st.time_input(
                "Start time",
                value=init_start_time,
                key=f"_{prefix}_start_time",
            )
        with c2:
            init_end = st.session_state.get(f"_{prefix}_end_date", end.date())
            init_end_time = st.session_state.get(f"_{prefix}_end_time", end.time())
            end_date = st.date_input(
                "End date",
                value=init_end,
                key=f"_{prefix}_end_date",
            )
            end_time = st.time_input(
                "End time",
                value=init_end_time,
                key=f"_{prefix}_end_time",
            )
        with c3:
            meeting_timezone = st.text_input(
                "Timezone",
                value=timezone_name or cfg.default_timezone,
                key=f"_{prefix}_timezone",
                help="IANA timezone, for example Asia/Kolkata.",
            )
            st.caption(f"Organizer: `{cfg.organizer_upn or '(not set)'}`")

        st.caption("Attendees — edit below or use quick-add buttons.")
        _render_attendee_tools(
            prefix=prefix,
            cfg=cfg,
            kind=kind,
            meeting_context=ctx,
        )
        attendees_raw = st.text_area(
            "Attendee emails",
            value=st.session_state.get(f"_{prefix}_attendees", ""),
            key=f"_{prefix}_attendees",
            height=70,
            help="Comma-separated. Defaults from workspace.yaml + optional assignees.",
        )

        start_dt = datetime.combine(_as_date(start_date), _as_time(start_time))
        end_dt = datetime.combine(_as_date(end_date), _as_time(end_time))
        if end_dt <= start_dt:
            st.error("Meeting end must be after start.")
            return

        draft = teams_schedule.build_meeting_draft(
            cfg,
            kind=kind,
            subject=subject,
            start=start_dt,
            end=end_dt,
            timezone_name=meeting_timezone,
            attendees=parse_attendees_text(attendees_raw),
            body=meeting_body,
            version=version,
        )

        preview_col, live_col, update_col, _ = st.columns([1, 1, 1, 1])
        existing_event_id = str(st.session_state.get(f"shared_teams_{kind}_event_id") or "").strip()
        with preview_col:
            if st.button(
                "Preview meeting",
                key=f"{prefix}_preview",
                use_container_width=True,
            ):
                _schedule_one(
                    prefix=prefix,
                    kind=kind,
                    cfg=cfg,
                    draft=draft,
                    dry_run=True,
                )
                st.rerun()
        with live_col:
            if st.button(
                "Schedule in Teams",
                key=f"{prefix}_schedule",
                type="primary",
                use_container_width=True,
                disabled=not cfg.can_schedule(),
                help="Requires MS_GRAPH_* in .env and teams_schedule.enabled=true",
            ):
                _schedule_one(
                    prefix=prefix,
                    kind=kind,
                    cfg=cfg,
                    draft=draft,
                    dry_run=False,
                )
                st.rerun()
        with update_col:
            if st.button(
                "Update scheduled meeting",
                key=f"{prefix}_update",
                use_container_width=True,
                disabled=not (cfg.can_schedule() and existing_event_id),
                help="PATCH the existing Outlook event (requires event ID from a prior schedule).",
            ):
                _schedule_one(
                    prefix=prefix,
                    kind=kind,
                    cfg=cfg,
                    draft=draft,
                    dry_run=False,
                    update_event_id=existing_event_id,
                )
                st.rerun()
        cancel_col, _ = st.columns([1, 3])
        with cancel_col:
            if st.button(
                "Cancel scheduled meeting",
                key=f"{prefix}_cancel",
                use_container_width=True,
                disabled=not (cfg.can_schedule() and existing_event_id),
            ):
                result = teams_schedule.cancel_meeting(cfg, existing_event_id, dry_run=False)
                st.session_state[f"{prefix}_result"] = result.to_dict()
                if result.ok:
                    for key in (
                        f"shared_teams_{kind}_event_id",
                        f"shared_teams_{kind}_url",
                        f"shared_teams_{kind}_web",
                    ):
                        st.session_state.pop(key, None)
                    from session_persist import persist_session

                    persist_session(dict(st.session_state), notify=True)
                st.rerun()

        _render_schedule_result(prefix, subject=subject)

        st.caption(
            "CLI test: `python orchestrator/zones/platform/ops/test_teams_schedule.py --kind "
            + kind
            + " --dry-run`  |  Settings -> Integrations to edit organizer/attendees."
        )


def render_teams_dual_schedule_panel(
    *,
    version: str,
    review_context: MeetingContext | None = None,
    deployment_context: MeetingContext | None = None,
    deployment_start: datetime | None = None,
    deployment_end: datetime | None = None,
    timezone_name: str | None = None,
) -> None:
    """Review + deployment meetings in one place (Service Ticket step)."""
    st.markdown("### Schedule release meetings")
    st.caption(
        "Both calls are pre-filled from this release. Edit time, attendees, or body, "
        "then preview or schedule each call."
    )

    review_ctx = review_context or MeetingContext(version=version, kind="review")
    deploy_ctx = deployment_context or MeetingContext(version=version, kind="deployment")

    tab_review, tab_deploy = st.tabs(["Review call", "Deployment call"])
    with tab_review:
        render_teams_schedule_panel(
            kind="review",
            version=version,
            meeting_context=review_ctx,
        )

    with tab_deploy:
        render_teams_schedule_panel(
            kind="deployment",
            version=version,
            default_start=deployment_start,
            default_end=deployment_end,
            timezone_name=timezone_name,
            meeting_context=deploy_ctx,
        )

    cfg = teams_schedule.load_schedule_config(config.TEAMS_SCHEDULE)
    if not cfg.can_schedule():
        return

    st.markdown("**Schedule both**")
    b1, b2, _ = st.columns([1, 1, 2])
    with b1:
        if st.button("Preview both meetings", key="teams_dual_preview", use_container_width=True):
            for kind in ("review", "deployment"):
                prefix = f"teams_{kind}"
                subject = st.session_state.get(f"_{prefix}_subject", default_subject(kind, version))
                body = st.session_state.get(f"_{prefix}_body", "")
                attendees = parse_attendees_text(st.session_state.get(f"_{prefix}_attendees", ""))
                sd = st.session_state.get(f"_{prefix}_start_date")
                st_t = st.session_state.get(f"_{prefix}_start_time")
                ed = st.session_state.get(f"_{prefix}_end_date")
                et = st.session_state.get(f"_{prefix}_end_time")
                tz = st.session_state.get(f"_{prefix}_timezone", cfg.default_timezone)
                if not (sd and st_t and ed and et):
                    st.warning(f"Set start/end for {kind} meeting first.")
                    continue
                start_dt = datetime.combine(_as_date(sd), _as_time(st_t))
                end_dt = datetime.combine(_as_date(ed), _as_time(et))
                draft = teams_schedule.build_meeting_draft(
                    cfg,
                    kind=kind,  # type: ignore[arg-type]
                    subject=subject,
                    start=start_dt,
                    end=end_dt,
                    timezone_name=tz,
                    attendees=attendees,
                    body=body,
                    version=version,
                )
                _schedule_one(
                    prefix=prefix,
                    kind=kind,  # type: ignore[arg-type]
                    cfg=cfg,
                    draft=draft,
                    dry_run=True,
                )
            st.rerun()
    with b2:
        if st.button("Schedule both in Teams", key="teams_dual_live", type="primary", use_container_width=True):
            errors: list[str] = []
            for kind in ("review", "deployment"):
                prefix = f"teams_{kind}"
                subject = st.session_state.get(f"_{prefix}_subject", default_subject(kind, version))
                body = st.session_state.get(f"_{prefix}_body", "")
                attendees = parse_attendees_text(st.session_state.get(f"_{prefix}_attendees", ""))
                sd = st.session_state.get(f"_{prefix}_start_date")
                st_t = st.session_state.get(f"_{prefix}_start_time")
                ed = st.session_state.get(f"_{prefix}_end_date")
                et = st.session_state.get(f"_{prefix}_end_time")
                tz = st.session_state.get(f"_{prefix}_timezone", cfg.default_timezone)
                if not (sd and st_t and ed and et):
                    errors.append(f"{kind}: missing start/end")
                    continue
                start_dt = datetime.combine(_as_date(sd), _as_time(st_t))
                end_dt = datetime.combine(_as_date(ed), _as_time(et))
                if end_dt <= start_dt:
                    errors.append(f"{kind}: end must be after start")
                    continue
                draft = teams_schedule.build_meeting_draft(
                    cfg,
                    kind=kind,  # type: ignore[arg-type]
                    subject=subject,
                    start=start_dt,
                    end=end_dt,
                    timezone_name=tz,
                    attendees=attendees,
                    body=body,
                    version=version,
                )
                _schedule_one(
                    prefix=prefix,
                    kind=kind,  # type: ignore[arg-type]
                    cfg=cfg,
                    draft=draft,
                    dry_run=False,
                )
            if errors:
                st.error("; ".join(errors))
            st.rerun()
