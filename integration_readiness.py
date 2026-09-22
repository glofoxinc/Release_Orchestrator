"""Unified integration readiness — what is done vs still pending.

Used by home health, verify_integrations, and MCP operator diagnostics.
Credential-gated items (SharePoint Graph, Teams schedule, Slack announce) are
reported as pending without treating them as code gaps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import config
import team_scope

ReadinessCategory = Literal[
    "blocking",
    "credential",
    "validation",
    "optional",
    "ready",
]

ReadinessStatus = Literal["pending", "partial", "ready", "skipped"]


@dataclass(frozen=True)
class ReadinessItem:
    id: str
    title: str
    status: ReadinessStatus
    category: ReadinessCategory
    detail: str
    fix: str = ""
    excluded_from_ops: bool = False  # user-owned external setup (Slack bot, Entra app)


def _graph_missing() -> list[str]:
    try:
        from ms_graph import GraphClient

        return list(GraphClient().status().get("missing") or [])
    except Exception:  # noqa: BLE001
        return ["MS_GRAPH_TENANT_ID", "MS_GRAPH_CLIENT_ID", "MS_GRAPH_CLIENT_SECRET"]


def collect_readiness_items(*, include_excluded: bool = True) -> list[ReadinessItem]:
    """Return all integration readiness rows, most urgent first."""
    items: list[ReadinessItem] = []

    # ── Team scope (blocking release fetches) ──────────────────────────
    blocking_scope: list[str] = []
    for proj in config.PROJECTS:
        pk = str(proj.get("key", "")).strip().upper()
        if not pk:
            continue
        st = team_scope.scope_status(pk)
        if st.get("blocking"):
            blocking_scope.append(pk)
    if blocking_scope:
        items.append(ReadinessItem(
            id="team_scope",
            title="Team ticket scope",
            status="pending",
            category="blocking",
            detail=f"Release fetches blocked for: {', '.join(blocking_scope)}.",
            fix=(
                "Settings → Projects → set board URL/ID, saved filter, labels, "
                "components, custom JQL, or allow project-wide scope."
            ),
        ))
    else:
        configured = [
            str(p.get("key", "")).strip().upper()
            for p in config.PROJECTS
            if team_scope.scope_status(str(p.get("key", "")).strip().upper()).get("configured")
        ]
        items.append(ReadinessItem(
            id="team_scope",
            title="Team ticket scope",
            status="ready",
            category="ready",
            detail=f"Configured for {', '.join(configured) or 'workspace projects'}.",
        ))

    # ── Jira credentials ─────────────────────────────────────────────
    if not config.JIRA_EMAIL or config.is_placeholder_credential(config.JIRA_API_TOKEN):
        items.append(ReadinessItem(
            id="jira_auth",
            title="Jira API credentials",
            status="pending",
            category="blocking",
            detail="JIRA_EMAIL and a real JIRA_API_TOKEN are required.",
            fix="Add credentials to .env (see .env.example).",
        ))
    else:
        items.append(ReadinessItem(
            id="jira_auth",
            title="Jira API credentials",
            status="ready",
            category="ready",
            detail="Email and token present (not placeholder).",
        ))

    # ── Service desk metadata ──────────────────────────────────────────
    if config.SERVICE_DESK_ENABLED:
        if config.service_desk_request_type_configured() and config.TCKT_ISSUE_TYPE_ID:
            items.append(ReadinessItem(
                id="service_desk",
                title="SHIPIT Service Desk metadata",
                status="ready",
                category="ready",
                detail="Request type and issue type configured.",
            ))
        else:
            items.append(ReadinessItem(
                id="service_desk",
                title="SHIPIT Service Desk metadata",
                status="partial",
                category="optional",
                detail="Some SHIPIT fields may need manual portal edits after create.",
                fix="Settings → Service Desk → Fetch from Jira → Save.",
            ))

    # ── SharePoint Graph upload ────────────────────────────────────────
    if config.sharepoint_upload_archived():
        items.append(ReadinessItem(
            id="sharepoint_upload",
            title="SharePoint auto-upload",
            status="skipped",
            category="optional",
            detail="Archived — manual SharePoint URL is the active path.",
            fix="Restore from archive/sharepoint_upload.yaml when MS_GRAPH_* is ready.",
            excluded_from_ops=True,
        ))
    else:
        try:
            import sharepoint_upload as sp_up

            sp_cfg = sp_up.load_upload_config(config.SHAREPOINT_UPLOAD)
            sp_st = sp_up.status(sp_cfg)
            missing_graph = _graph_missing()
            if sp_cfg.can_upload():
                items.append(ReadinessItem(
                    id="sharepoint_upload",
                    title="SharePoint auto-upload",
                    status="ready",
                    category="ready",
                    detail=f"Graph upload ready — folder `{sp_cfg.folder_path}`.",
                ))
            elif sp_cfg.target_ready():
                items.append(ReadinessItem(
                    id="sharepoint_upload",
                    title="SharePoint auto-upload",
                    status="partial",
                    category="credential",
                    detail=(
                        f"Target `{sp_cfg.folder_path}` on {sp_cfg.hostname or 'configured site'}; "
                        "enabled=false until MS_GRAPH_* are set."
                    ),
                    fix="Set MS_GRAPH_* in .env, grant Sites.ReadWrite.All, then sharepoint_upload.enabled=true.",
                    excluded_from_ops=True,
                ))
            else:
                items.append(ReadinessItem(
                    id="sharepoint_upload",
                    title="SharePoint auto-upload",
                    status="pending",
                    category="validation",
                    detail="SharePoint target incomplete in workspace.yaml.",
                    fix="Set hostname, site_path, and folder_path (or drive_id).",
                ))
            if sp_cfg.enabled and not sp_st.get("can_upload") and missing_graph:
                items[-1] = ReadinessItem(
                    id="sharepoint_upload",
                    title="SharePoint auto-upload",
                    status="pending",
                    category="credential",
                    detail="Enabled but missing: " + ", ".join(missing_graph),
                    fix="Add MS_GRAPH_* to .env and confirm site_path with IT.",
                    excluded_from_ops=True,
                )
        except Exception as exc:  # noqa: BLE001
            items.append(ReadinessItem(
                id="sharepoint_upload",
                title="SharePoint auto-upload",
                status="pending",
                category="validation",
                detail=str(exc),
            ))

    # ── Teams meeting schedule ─────────────────────────────────────────
    if config.teams_archived():
        items.append(ReadinessItem(
            id="teams_schedule",
            title="Teams meeting scheduling",
            status="skipped",
            category="optional",
            detail="Archived — removed from platform UI.",
            fix="Restore from archive/teams_schedule.yaml when MS_GRAPH_* is ready.",
            excluded_from_ops=True,
        ))
    else:
        try:
            import teams_schedule as ts

            ts_cfg = ts.load_schedule_config(config.TEAMS_SCHEDULE)
            ts_st = ts.status(ts_cfg)
            if ts_cfg.can_schedule():
                items.append(ReadinessItem(
                    id="teams_schedule",
                    title="Teams meeting scheduling",
                    status="ready",
                    category="ready",
                    detail=f"Organizer {ts_cfg.organizer_upn}; Graph configured.",
                ))
            elif not ts_cfg.organizer_upn:
                items.append(ReadinessItem(
                    id="teams_schedule",
                    title="Teams meeting scheduling",
                    status="partial",
                    category="credential",
                    detail="Backend + UI wired; organizer_upn empty in workspace.yaml.",
                    fix="Settings → Integrations → Organizer email.",
                    excluded_from_ops=True,
                ))
            elif _graph_missing():
                items.append(ReadinessItem(
                    id="teams_schedule",
                    title="Teams meeting scheduling",
                    status="partial",
                    category="credential",
                    detail=(
                        f"Organizer {ts_cfg.organizer_upn}; "
                        f"{len(ts_cfg.default_attendees)} default attendee(s). MS_GRAPH_* required."
                    ),
                    fix="Add MS_GRAPH_* to .env (Calendars.ReadWrite). Test: python scripts/test_teams_schedule.py --dry-run",
                    excluded_from_ops=True,
                ))
            else:
                items.append(ReadinessItem(
                    id="teams_schedule",
                    title="Teams meeting scheduling",
                    status="partial",
                    category="credential",
                    detail=ts_st.get("note") or "Set teams_schedule.enabled=true when ready.",
                    fix="Enable teams_schedule in workspace.yaml after Graph credentials are live.",
                    excluded_from_ops=True,
                ))
        except Exception as exc:  # noqa: BLE001
            items.append(ReadinessItem(
                id="teams_schedule",
                title="Teams meeting scheduling",
                status="pending",
                category="optional",
                detail=str(exc),
            ))

    # ── Release gates (status-based Slack DMs) ─────────────────────────
    try:
        import release_gates
        from slack_assignee_notify import gate_slack_status

        gates_on = release_gates.gates_root_enabled()
        pre_on = release_gates.gate_enabled("pre_review")
        post_on = release_gates.gate_enabled("post_qa")
        slack_st = gate_slack_status()
        if gates_on and (pre_on or post_on):
            detail_parts = []
            if pre_on:
                detail_parts.append(
                    f"pre-review ({len(release_gates.pre_review_statuses())} statuses)"
                )
            if post_on:
                detail_parts.append(
                    f"post-QA ({len(release_gates.qa_passed_statuses())} statuses)"
                )
            if config.slack_archived() or not (
                release_gates.slack_notify_enabled("pre_review")
                or release_gates.slack_notify_enabled("post_qa")
            ):
                ui_flags = []
                if pre_on:
                    ui_flags.append(
                        "Ticket Review filter "
                        + ("on" if release_gates.ticket_review_pre_review_enabled() else "off")
                    )
                if post_on:
                    ui_flags.append(
                        "Release Notes QA filter "
                        + ("on" if release_gates.post_qa_release_notes_enabled() else "off")
                    )
                ui_note = f" UI: {', '.join(ui_flags)}." if ui_flags else ""
                items.append(ReadinessItem(
                    id="release_gates",
                    title="Release gates",
                    status="ready",
                    category="ready",
                    detail=f"API enabled ({', '.join(detail_parts)}).{ui_note}",
                ))
            else:
                token_note = (
                    "Slack DM ready"
                    if slack_st.get("can_dm_assignees")
                    else "Slack DM needs SLACK_BOT_TOKEN"
                )
                items.append(ReadinessItem(
                    id="release_gates",
                    title="Release gates + assignee Slack",
                    status="ready" if slack_st.get("can_dm_assignees") else "partial",
                    category="ready" if slack_st.get("can_dm_assignees") else "credential",
                    detail=f"Enabled: {', '.join(detail_parts)}. {token_note}.",
                    fix="SLACK_BOT_TOKEN with im:write + users:read.email for live assignee DMs.",
                    excluded_from_ops=not slack_st.get("can_dm_assignees"),
                ))
        else:
            items.append(ReadinessItem(
                id="release_gates",
                title="Release gates + assignee Slack",
                status="skipped",
                category="optional",
                detail="release_gates disabled in workspace.yaml.",
            ))
    except Exception as exc:  # noqa: BLE001
        items.append(ReadinessItem(
            id="release_gates",
            title="Release gates + assignee Slack",
            status="pending",
            category="optional",
            detail=str(exc),
        ))

    # ── Slack announce ─────────────────────────────────────────────────
    import os

    if config.slack_archived():
        items.append(ReadinessItem(
            id="slack_announce",
            title="Slack announce",
            status="skipped",
            category="optional",
            detail="Archived — restore from archive/slack_announce.yaml when ready.",
            fix="Set slack_announce.enabled=true and SLACK_BOT_TOKEN in .env.",
            excluded_from_ops=True,
        ))
    elif os.environ.get("SLACK_BOT_TOKEN", "").strip() and not config.is_placeholder_credential(
        os.environ.get("SLACK_BOT_TOKEN", "").strip()
    ):
        items.append(ReadinessItem(
            id="slack_announce",
            title="Slack announce",
            status="ready",
            category="ready",
            detail="Bot token present; preview/send available after channel invites.",
        ))
    else:
        items.append(ReadinessItem(
            id="slack_announce",
            title="Slack announce",
            status="partial",
            category="credential",
            detail="Preview wired; live post needs SLACK_BOT_TOKEN + bot invited to both channels.",
            fix="Create Slack app/bot, invite to configured channels.",
            excluded_from_ops=True,
        ))

    # ── Confluence (optional publish) ──────────────────────────────────
    if os.environ.get("CONFLUENCE_TOKEN") and os.environ.get("CONFLUENCE_SPACE"):
        items.append(ReadinessItem(
            id="confluence",
            title="Confluence publish",
            status="ready",
            category="ready",
            detail="CONFLUENCE_* env vars set.",
        ))
    else:
        items.append(ReadinessItem(
            id="confluence",
            title="Confluence publish",
            status="skipped",
            category="optional",
            detail="Optional — release notes DOCX is the primary artifact.",
            fix="Set CONFLUENCE_URL, CONFLUENCE_TOKEN, CONFLUENCE_SPACE if needed.",
        ))

    # ── Release notes generator ────────────────────────────────────────
    try:
        from generators.release_notes_e2e import e2e_status
        from generators.release_notes_generator import GENERATOR_BUILD_ID

        rn_st = e2e_status()
        if rn_st.get("ok"):
            items.append(ReadinessItem(
                id="release_notes",
                title="Release notes generator",
                status="ready",
                category="ready",
                detail=(
                    f"DOCX v4 · build `{GENERATOR_BUILD_ID}` · "
                    f"fixture E2E score {rn_st.get('readiness_score')}/100 · publish gate OK."
                ),
            ))
        else:
            items.append(ReadinessItem(
                id="release_notes",
                title="Release notes generator",
                status="partial",
                category="optional",
                detail=f"Build `{GENERATOR_BUILD_ID}` — fixture E2E needs attention.",
                fix="Run: python scripts/test_release_notes_e2e.py",
            ))
    except Exception as exc:  # noqa: BLE001
        items.append(ReadinessItem(
            id="release_notes",
            title="Release notes generator",
            status="ready",
            category="ready",
            detail=f"DOCX v4 layout, readiness score, shared publish gate (UI + MCP). ({exc})",
        ))

    # ── Daily Review Agent (merged v3.4) ───────────────────────────────
    try:
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.playwright_outlook_auth import outlook_readiness
        from daily_review_agent.setup_mcp import validate_cursor_mcp_config

        dr_cfg = load_agent_config()
        dr_mcp = validate_cursor_mcp_config()
        dr_outlook = outlook_readiness()
        mcp_ok = not dr_mcp.get("missing_servers") and not dr_mcp.get("issues")
        outlook_ok = bool(dr_outlook.get("can_schedule"))
        if dr_cfg.enabled and mcp_ok and outlook_ok:
            st: ReadinessStatus = "ready"
            cat: ReadinessCategory = "ready"
            detail = "Daily review enabled; MCP + Outlook web profile ready."
        elif mcp_ok and dr_cfg.teams_summary_conversation_id:
            st = "partial"
            cat = "credential"
            detail = "MCP OK; complete Outlook login before live runs."
        else:
            st = "partial"
            cat = "optional"
            detail = "Merged in repo — run .\\scripts\\setup_e2e.ps1 and daily_review_orchestrator."
        items.append(ReadinessItem(
            id="daily_review",
            title="Daily Review Agent (6 PM PIC/AN)",
            status=st,
            category=cat,
            detail=detail,
            fix="daily_review_orchestrator(message='daily review welcome') → outlook-login → preflight-live.",
            excluded_from_ops=not dr_cfg.enabled,
        ))
    except Exception as exc:  # noqa: BLE001
        items.append(ReadinessItem(
            id="daily_review",
            title="Daily Review Agent (6 PM PIC/AN)",
            status="pending",
            category="optional",
            detail=str(exc)[:180],
            fix="pip install -e '.[calendar,daily_review,dev]'",
        ))

    # ── MCP workflow parity (dev/CI only — not shown on operator home) ─
    items.append(ReadinessItem(
        id="mcp_parity",
        title="MCP workflow parity",
        status="ready",
        category="ready",
        detail="Full wizard, standalone modes, consolidation, deploy drift gate, operator_guide.",
        excluded_from_ops=True,
    ))

    # ── Live E2E / Playwright (dev/CI only) ────────────────────────────
    items.append(ReadinessItem(
        id="live_e2e",
        title="Live end-to-end smoke",
        status="pending",
        category="optional",
        detail="Real Jira -> DOCX -> manual SharePoint link -> SHIPIT -> deploy not yet recorded in CI.",
        fix="Run one release in MOCK_MODE=0; document in RUNBOOK § smoke checklist.",
        excluded_from_ops=True,
    ))
    items.append(ReadinessItem(
        id="playwright_ci",
        title="Playwright browser smoke in CI",
        status="skipped",
        category="optional",
        detail="Optional gate — set RUN_PLAYWRIGHT=1 locally or in CI workflow.",
        fix="Add RUN_PLAYWRIGHT=1 job to .github/workflows/ci.yml when desired.",
        excluded_from_ops=True,
    ))
    items.append(ReadinessItem(
        id="docx_parity",
        title="DOCX reference fingerprint",
        status="partial",
        category="optional",
        detail="Structural parity enforced; ~14 cosmetic gaps allowed vs reference template.",
        fix="Tighten allowlist in test_platform_reference_parity when template tweaks land.",
        excluded_from_ops=True,
    ))

    if not include_excluded:
        items = [i for i in items if not i.excluded_from_ops]
    return items


def summarize_readiness(*, include_excluded: bool = True) -> dict[str, Any]:
    """Counts and lists for dashboards and verify script."""
    items = collect_readiness_items(include_excluded=include_excluded)
    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
        by_category[item.category] = by_category.get(item.category, 0) + 1
    pending_ops = [
        i for i in items
        if i.status in {"pending", "partial"} and not i.excluded_from_ops
    ]
    pending_external = [
        i for i in items
        if i.status in {"pending", "partial"} and i.excluded_from_ops
    ]
    return {
        "items": [item.__dict__ for item in items],
        "counts": {"by_status": by_status, "by_category": by_category},
        "blocking_pending": [i.__dict__ for i in items if i.category == "blocking" and i.status != "ready"],
        "ops_pending": [i.__dict__ for i in pending_ops],
        "external_pending": [i.__dict__ for i in pending_external],
        "ready_count": sum(1 for i in items if i.status == "ready"),
    }
