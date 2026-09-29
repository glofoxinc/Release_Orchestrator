"""Setup health checks for new-user onboarding."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

import config
from sharepoint_url import sharepoint_validation_message, validate_sharepoint_url
from release_platform.ui.helpers import esc, projects_blocking_scope


@dataclass(frozen=True)
class SetupIssue:
    level: str  # "error" | "warning" | "info"
    title: str
    detail: str
    fix: str


def collect_setup_issues() -> list[SetupIssue]:
    """Return actionable setup gaps ordered by severity."""
    issues: list[SetupIssue] = []

    if not config.JIRA_EMAIL or config.is_placeholder_credential(config.JIRA_API_TOKEN):
        issues.append(SetupIssue(
            level="error",
            title="Jira credentials missing",
            detail="The app cannot call Jira without email and a real API token.",
            fix="Add JIRA_EMAIL and JIRA_API_TOKEN to .env (not the placeholder), then refresh.",
        ))

    if not config.PROJECTS:
        issues.append(SetupIssue(
            level="error",
            title="No Jira projects configured",
            detail="Release pickers need at least one project (e.g. PIC, AN).",
            fix="Open Settings → Projects and add your project keys.",
        ))

    missing_scope = projects_blocking_scope()
    if missing_scope:
        issues.append(SetupIssue(
            level="error",
            title="Team ticket scope not configured",
            detail=(
                "Release fetches are blocked for: "
                + ", ".join(missing_scope)
                + ". Version alone is not a team boundary when multiple boards share a fix version."
            ),
            fix=(
                "Settings → Projects → set board URL/ID, saved filter id, labels, components, "
                "custom JQL, or explicitly allow project-wide scope."
            ),
        ))

    if config.SERVICE_DESK_ENABLED:
        missing_sd: list[str] = []
        if not config.TCKT_ISSUE_TYPE_ID:
            missing_sd.append("issue_type_id")
        if not config.TCKT_SERVICE_DESK_ID:
            missing_sd.append("service_desk_id")
        if not config.TCKT_REQUEST_TYPE_ID:
            missing_sd.append("request_type_id")
        approver_field = (config.TCKT_FIELDS.get("approvers") or "").strip()
        approver_groups = config.TCKT_DEFAULTS.get("approver_groups") or []
        if not approver_field and not approver_groups:
            missing_sd.append("approver_groups or fields.approvers")
        if missing_sd:
            issues.append(SetupIssue(
                level="warning",
                title="SHIPIT configuration incomplete",
                detail="Missing: " + ", ".join(missing_sd),
                fix="Settings → Service Desk — fetch metadata from Jira and save.",
            ))
        elif not config.service_desk_request_type_configured():
            issues.append(SetupIssue(
                level="info",
                title="SHIPIT Request Type",
                detail=(
                    "Tickets can be created; set Request Type manually in Jira if auto-set is unavailable."
                ),
                fix="Settings → Service Desk → Fetch from Jira → Save.",
            ))

    # Slack token / channel wiring is optional for day-to-day use — users set it
    # up when they want announce send. Do not surface it as a home-page warning.

    if not config.slack_archived():
        for warning in getattr(config, "CONFIG_WARNINGS", []) or []:
            issues.append(SetupIssue(
                level="warning",
                title="Workspace Slack schema",
                detail=warning,
                fix="Fix slack_announce in workspace.yaml (channels/cc keys).",
            ))

    for msg in config.placeholder_credential_issues():
        # Avoid duplicating the hard Jira error already added above.
        # Slack token placeholders are intentional until announce is configured —
        # do not show them on the home health panel.
        if "JIRA_API_TOKEN" in msg and any(i.title == "Jira credentials missing" for i in issues):
            continue
        if "SLACK_BOT_TOKEN" in msg:
            continue
        issues.append(SetupIssue(
            level="warning",
            title="Placeholder credentials",
            detail=msg,
            fix="Replace example values in .env with real tokens.",
        ))

    sample_sp = ""
    try:
        sample_sp = str(
            st.session_state.get("shared_sharepoint_url")
            or st.session_state.get("stk_sharepoint")
            or ""
        )
    except Exception:  # noqa: BLE001 — health works outside a Streamlit script run
        sample_sp = ""
    if sample_sp and not validate_sharepoint_url(sample_sp):
        issues.append(SetupIssue(
            level="warning",
            title="SharePoint URL shape",
            detail=sharepoint_validation_message(sample_sp)
            or "Current SharePoint URL failed host/link validation.",
            fix="Paste a *.sharepoint.com document link (sites/Doc.aspx/:w:/.docx).",
        ))
    elif sample_sp and not validate_sharepoint_url(sample_sp, require_link_shape=True):
        issues.append(SetupIssue(
            level="info",
            title="SharePoint link shape soft warning",
            detail=sharepoint_validation_message(sample_sp),
            fix="Prefer a direct document link so SHIPIT description hyperlinks stay clickable.",
        ))

    try:
        import sharepoint_upload as sp_up

        upload_cfg = sp_up.load_upload_config(config.SHAREPOINT_UPLOAD)
        upload_status = sp_up.status(upload_cfg)
        if upload_cfg.enabled and not upload_status.get("can_upload"):
            missing = (upload_status.get("graph") or {}).get("missing") or []
            detail = "SharePoint auto-upload is enabled but not ready."
            if missing:
                detail += " Missing: " + ", ".join(missing)
            elif not upload_status.get("target_ready"):
                detail += " Set hostname/site_path or drive_id in workspace.yaml."
            issues.append(SetupIssue(
                level="warning",
                title="SharePoint Graph upload not ready",
                detail=detail,
                fix="Add MS_GRAPH_* to .env and verify sharepoint_upload targets in Settings/workspace.yaml.",
            ))
        elif upload_cfg.target_ready() and not upload_cfg.enabled:
            issues.append(SetupIssue(
                level="info",
                title="SharePoint upload target configured",
                detail=(
                    f"Folder `{upload_cfg.folder_path}` on {upload_cfg.hostname or 'configured site'} "
                    "is ready. Set sharepoint_upload.enabled=true after MS_GRAPH_* credentials are added."
                ),
                fix="Add MS_GRAPH_TENANT_ID, MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET to .env.",
            ))
    except Exception:  # noqa: BLE001 — health panel must not crash
        pass

    if not any(i.level in {"error", "warning"} for i in issues):
        issues.append(SetupIssue(
            level="info",
            title="Setup looks good",
            detail="Core configuration is present. Start with Ticket Review on the home page.",
            fix="Pick a release, review tickets, then continue to Release Notes or Service Ticket.",
        ))

    return issues


def render_integration_readiness_expander(*, include_dev_items: bool = False) -> None:
    """Expandable checklist of integration readiness (Settings / CLI companion)."""
    from integration_readiness import collect_readiness_items

    items = collect_readiness_items(include_excluded=include_dev_items)
    ops_pending = [
        i for i in items
        if i.status in {"pending", "partial"} and not i.excluded_from_ops
    ]
    external = [
        i for i in items
        if i.status in {"pending", "partial"} and i.excluded_from_ops
    ]
    ready = [i for i in items if i.status == "ready"]

    with st.expander(
        f"Integration checklist — {len(ready)} ready, {len(ops_pending)} in-repo, "
        f"{len(external)} external setup",
        expanded=bool(ops_pending),
    ):
        if ops_pending:
            st.markdown("**In-repo / ops (actionable here)**")
            for item in ops_pending:
                line = f"- **{esc(item.title)}** — {esc(item.detail)}"
                if item.fix:
                    line += f"  \n  *Fix:* {esc(item.fix)}"
                st.markdown(line)
        if external:
            st.markdown("**External setup (IT / Slack admin — excluded from code work)**")
            for item in external:
                line = f"- **{esc(item.title)}** — {esc(item.detail)}"
                if item.fix:
                    line += f"  \n  *Fix:* {esc(item.fix)}"
                st.markdown(line)
        if not ops_pending and not external:
            st.success("All tracked integrations are ready or optional.")
        st.caption(
            "Run `python scripts/verify_integrations.py --check=readiness` for the CLI view."
        )


def render_production_readiness_panel(*, expanded: bool = False) -> None:
    """Shared VERIFIED / UNVERIFIED / OPERATOR report (MCP + platform)."""
    import production_readiness as pr

    report = pr.assess_production_readiness(surface="platform")
    pct = report.get("automated_score_pct", 0)
    ready = report.get("production_ready")
    delivery = report.get("slack_delivery", "")

    label = f"Production readiness — {pct}% automated"
    if ready:
        label += " · **Ready**"
    with st.expander(label, expanded=expanded or not ready):
        if ready:
            st.success("Production ready — automated checks passed.")
        elif report.get("platform_ready"):
            st.info("Platform E2E ready — complete one-time operator checks below.")
        else:
            st.warning("Setup incomplete — fix blocking items.")

        for row in report.get("verified") or []:
            st.markdown(f"✅ **{esc(row['name'])}** — {esc(row['detail'])}")
        for row in report.get("unverified") or []:
            st.markdown(f"⬜ **{esc(row['name'])}** — {esc(row['detail'])}")
        for row in report.get("operator_required") or []:
            st.markdown(f"👤 **{esc(row['name'])}** — {esc(row['detail'])}")

        if delivery == "cursor_slack_mcp":
            st.caption(
                "Slack Step 6: use **Cursor Slack MCP** in chat — no SLACK_BOT_TOKEN in .env."
            )
        signoffs = report.get("operator_signoffs") or {}
        if report.get("launch_complete"):
            st.success("Launch complete — operator sign-offs recorded.")
        elif signoffs.get("missing"):
            st.markdown("**Operator sign-offs (one-time):**")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Mark SHIPIT dry-run done", key="signoff_shipit"):
                    import operator_signoff as osign

                    osign.record_signoff(osign.SIGNOFF_SHIPIT_DRY_RUN, detail="Marked on platform")
                    st.rerun()
            with c2:
                if st.button("Mark Slack live post done", key="signoff_slack"):
                    import operator_signoff as osign

                    osign.record_signoff(osign.SIGNOFF_SLACK_LIVE, detail="Marked on platform")
                    st.rerun()
        st.caption(
            "MCP: **production ready** · **shipit confirmed** · **slack confirmed** · "
            "`python scripts/complete_launch.py`"
        )


def render_setup_health_panel(*, operator_mode: bool = False) -> None:
    """Show setup status. Operator home: blocking errors only; Settings: full detail."""
    issues = collect_setup_issues()
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    infos = [i for i in issues if i.level == "info"]

    if operator_mode:
        if errors:
            st.error(
                f"**Action required** — {len(errors)} setup issue(s) must be fixed before you can run releases."
            )
            for issue in errors:
                st.markdown(
                    f"⛔ **{esc(issue.title)}** — {esc(issue.detail)}  \n"
                    f"*Fix:* {esc(issue.fix)}",
                )
            if st.button("Open Settings", key="home_open_settings", type="primary"):
                st.session_state["active_app"] = "settings"
                st.rerun()
        else:
            st.success("**Ready** — Jira is connected and your team scope is configured.")
        return

    if errors:
        st.error(f"**Setup incomplete** — {len(errors)} blocking issue(s).")
    elif warnings:
        st.warning(f"**Setup mostly ready** — {len(warnings)} item(s) to review.")
    else:
        st.success("**Setup complete** — ready to run release workflows.")

    show = errors + warnings + infos
    for issue in show:
        icon = {"error": "⛔", "warning": "⚠️", "info": "ℹ️"}.get(issue.level, "•")
        st.markdown(
            f"{icon} **{esc(issue.title)}** — {esc(issue.detail)}  \n"
            f"*Fix:* {esc(issue.fix)}",
        )

    if (errors or warnings) and st.button("Open Settings", key="home_open_settings", type="secondary"):
        st.session_state["active_app"] = "settings"
        st.rerun()
