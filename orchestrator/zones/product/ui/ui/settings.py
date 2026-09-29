"""Settings / Admin Setup — configure workspace.yaml through the UI."""

from __future__ import annotations

import os

import requests
import streamlit as st
import yaml
import json
from requests.auth import HTTPBasicAuth

import config
import jira_client
import team_scope
import teams_schedule
from ms_graph import GraphClient
from release_platform.ui.health import (
    render_integration_readiness_expander,
    render_production_readiness_panel,
    render_setup_health_panel,
)
from release_platform.ui.helpers import (
    esc,
    save_and_reload_env,
    ss_default,
    validate_workspace_projects,
    workflow_blocked_by_scope,
)


def _ws_path() -> str:
    return config.get_active_workspace_path()


def _load_raw() -> dict:
    path = _ws_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return raw.get("workspace", raw)
    return {}


def _save_raw(ws: dict) -> None:
    path = _ws_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"workspace": ws}, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _go_home() -> None:
    st.session_state.pop("active_app", None)
    st.rerun()


def render() -> None:
    st.markdown("## \u2699\ufe0f Workspace Settings")
    st.markdown(f"Editing **{esc(config.WORKSPACE_NAME)}** workspace configuration.")

    ws = _load_raw()

    ss_default("_cfg_step", 1)
    step = st.session_state["_cfg_step"]

    tab_labels = ["General", "Projects", "Service Desk", "Deployment", "Release Notes", "Apps", "Integrations"]
    tabs = st.tabs(tab_labels)

    teams_ws = ws.get("teams_schedule", {})
    sp_ws = ws.get("sharepoint_upload", {})

    # ── Tab 1: General ──────────────────────────────────────────────
    with tabs[0]:
        render_setup_health_panel(operator_mode=False)
        render_production_readiness_panel(expanded=True)
        render_integration_readiness_expander(include_dev_items=True)
        st.markdown("---")
        st.markdown("### Workspace Identity")
        new_name = st.text_input(
            "Workspace Name",
            value=ws.get("name", ""),
            placeholder="My Team",
            key="_cfg_name",
            help="Display name shown in the sidebar and home page.",
        )

        st.markdown("### Jira Connection")
        jira = ws.get("jira", {})
        new_url = st.text_input(
            "Jira Base URL",
            value=jira.get("base_url", ""),
            placeholder="https://yourorg.atlassian.net",
            key="_cfg_url",
            help="Your organization's Atlassian cloud URL.",
        )
        st.caption(f"Current email: **{esc(config.JIRA_EMAIL or 'not set')}**")
        st.caption("Email and API token are stored in `.env`, not in workspace.yaml.")

        new_email = st.text_input(
            "Change Email (optional)",
            value="",
            placeholder="Leave blank to keep current",
            key="_cfg_email",
            help="Only fill to change the stored email.",
        )
        new_token = st.text_input(
            "Change API Token (optional)",
            value="",
            type="password",
            placeholder="Leave blank to keep current",
            key="_cfg_token",
            help="Only fill to change the stored API token.",
        )

        if st.button("Test Connection", key="_cfg_test"):
            test_url = new_url or jira.get("base_url", config.JIRA_BASE_URL)
            test_email = new_email or config.JIRA_EMAIL
            test_token = new_token or config.JIRA_API_TOKEN
            try:
                resp = requests.get(
                    f"{test_url}/rest/api/3/myself",
                    auth=HTTPBasicAuth(test_email, test_token),
                    headers={"Accept": "application/json"},
                    timeout=10,
                )
                if resp.ok:
                    user = resp.json()
                    st.success(f"Connected as **{user.get('displayName', '?')}** ({user.get('emailAddress', '?')})")
                else:
                    st.error(f"Connection failed: {resp.status_code} {resp.reason}")
            except Exception as exc:
                st.error(f"Connection error: {exc}")

    # ── Tab 2: Projects ─────────────────────────────────────────────
    with tabs[1]:
        st.markdown("### Managed Projects")
        st.caption(
            "Each project needs a **team scope** (board, saved filter, labels, components, "
            "or custom JQL) so release-version fetches cannot pull another team's tickets."
        )
        blocked, blocking_keys = workflow_blocked_by_scope()
        if blocked:
            st.error(
                "Ticket fetching is blocked until scope is configured for: "
                + ", ".join(blocking_keys)
            )

        projects = ws.get("projects", [])
        updated_projects = []
        for idx, proj in enumerate(projects):
            pk = proj.get("key", "?")
            scope_raw = proj.get("scope") if isinstance(proj.get("scope"), dict) else team_scope.default_scope_dict()
            scope_state = team_scope.scope_status(pk, scope=team_scope.parse_scope(scope_raw))
            state_label = {
                "configured": "Configured",
                "project_wide": "Project-wide (explicit)",
                "invalid": "Invalid",
                "blocking": "Blocking",
            }.get(scope_state["state"], scope_state["state"])

            with st.expander(
                f"**{pk}** — {proj.get('name', '')} · Scope: {state_label}",
                expanded=scope_state["blocking"],
            ):
                c1, c2 = st.columns(2)
                with c1:
                    new_key = st.text_input(
                        "Project Key",
                        value=proj.get("key", ""),
                        key=f"_cfg_pk_{idx}",
                        help="Jira project key (e.g. PIC, AN).",
                    )
                    new_pname = st.text_input(
                        "Display Name",
                        value=proj.get("name", ""),
                        key=f"_cfg_pn_{idx}",
                        help="Human-readable project name for the UI.",
                    )
                with c2:
                    new_mc = st.checkbox(
                        "Multi-Client",
                        value=proj.get("multi_client", False),
                        key=f"_cfg_mc_{idx}",
                        help="If checked, tickets are grouped by client name parsed from the title.",
                    )
                    new_ce = st.selectbox(
                        "Client Extraction",
                        ["title_prefix", "none"],
                        index=0 if proj.get("client_extraction", "none") == "title_prefix" else 1,
                        key=f"_cfg_ce_{idx}",
                        help="How to extract client name: 'title_prefix' uses text before first dash.",
                    )

                st.markdown("#### Team scope")
                sc1, sc2 = st.columns(2)
                with sc1:
                    board_id = st.text_input(
                        "Board URL or ID",
                        value=str(scope_raw.get("board_id", "")),
                        key=f"_cfg_scope_board_{idx}",
                        help="Jira board URL/ID; resolves to its saved filter.",
                    )
                    filter_id = st.text_input(
                        "Saved filter ID",
                        value=str(scope_raw.get("filter_id", "")),
                        key=f"_cfg_scope_filter_{idx}",
                        help="Use when you already know the filter id (filter = … in JQL).",
                    )
                    labels_csv = st.text_input(
                        "Labels (any)",
                        value=", ".join(scope_raw.get("labels_any") or []),
                        key=f"_cfg_scope_labels_{idx}",
                        help="Comma-separated labels; matched with OR inside the scope clause.",
                    )
                with sc2:
                    components_csv = st.text_input(
                        "Components (any)",
                        value=", ".join(scope_raw.get("components_any") or []),
                        key=f"_cfg_scope_components_{idx}",
                        help="Comma-separated component names.",
                    )
                    custom_jql = st.text_area(
                        "Additional JQL",
                        value=str(scope_raw.get("jql", "")),
                        key=f"_cfg_scope_jql_{idx}",
                        help="Extra AND clause only — no project/fixVersion/ORDER BY.",
                    )
                    allow_wide = st.checkbox(
                        "Allow project-wide scope (explicit)",
                        value=bool(scope_raw.get("allow_project_wide", False)),
                        key=f"_cfg_scope_wide_{idx}",
                        help="Only when this team truly owns every ticket on the fix version.",
                    )
                    owns_version = st.checkbox(
                        "Team owns whole Jira version (mark released)",
                        value=bool(scope_raw.get("owns_version", False)),
                        key=f"_cfg_scope_own_{idx}",
                        help="Required to mark the Jira fix version Released after deploy.",
                    )

                if scope_state["errors"]:
                    for err in scope_state["errors"]:
                        st.warning(err)

                test_version = st.text_input(
                    "Optional version id for scope test",
                    value="",
                    key=f"_cfg_scope_ver_{idx}",
                    help="When set, preflight count uses project + fixVersion + scope.",
                )
                if st.button("Test team scope", key=f"_cfg_scope_test_{idx}"):
                    draft_scope = team_scope.parse_scope({
                        "board_id": board_id,
                        "filter_id": filter_id,
                        "labels_any": [x.strip() for x in labels_csv.split(",") if x.strip()],
                        "components_any": [x.strip() for x in components_csv.split(",") if x.strip()],
                        "jql": custom_jql,
                        "allow_project_wide": allow_wide,
                        "owns_version": owns_version,
                    })
                    struct_errors = team_scope.validate_scope_structure(
                        draft_scope, project_key=new_key.strip().upper() or pk,
                    )
                    if struct_errors:
                        for err in struct_errors:
                            st.error(err)
                    else:
                        # Temporarily evaluate against draft scope via direct Jira call.
                        pk_test = (new_key or pk).strip().upper()
                        saved = config.PROJECTS
                        try:
                            patched = []
                            for p in config.PROJECTS:
                                if str(p.get("key", "")).strip().upper() == pk_test:
                                    patched.append({
                                        **p,
                                        "scope": team_scope.scope_dict_from_scope(draft_scope),
                                    })
                                else:
                                    patched.append(p)
                            config.PROJECTS = patched
                            result = jira_client.validate_team_scope(
                                pk_test,
                                version_id=test_version.strip(),
                            )
                        finally:
                            config.PROJECTS = saved

                        if result.get("blocking"):
                            st.error("; ".join(result.get("errors") or ["Scope invalid."]))
                        else:
                            st.success(
                                f"Scope OK ({result.get('scope_type')}). "
                                f"Preflight count: {result.get('preflight_total', 0)}."
                            )
                            sample = result.get("sample_keys") or []
                            if sample:
                                st.caption("Sample tickets: " + ", ".join(sample))

                remove = st.checkbox("Remove this project", key=f"_cfg_rm_{idx}")
                if not remove:
                    updated_projects.append({
                        "key": new_key,
                        "name": new_pname,
                        "multi_client": new_mc,
                        "client_extraction": new_ce,
                        "scope": {
                            "board_id": board_id.strip(),
                            "filter_id": filter_id.strip(),
                            "labels_any": [x.strip() for x in labels_csv.split(",") if x.strip()],
                            "components_any": [x.strip() for x in components_csv.split(",") if x.strip()],
                            "jql": custom_jql.strip(),
                            "allow_project_wide": allow_wide,
                            "owns_version": owns_version,
                        },
                    })

        st.markdown("#### Add New Project")
        c1, c2, c3 = st.columns([2, 3, 2])
        with c1:
            add_key = st.text_input(
                "Key",
                placeholder="PROJ",
                key="_cfg_add_key",
                help="Jira project key (uppercase).",
            )
        with c2:
            add_name = st.text_input(
                "Name",
                placeholder="Project Name",
                key="_cfg_add_name",
                help="Display name for the project.",
            )
        with c3:
            add_mc = st.checkbox(
                "Multi-Client",
                key="_cfg_add_mc",
                help="Check if this project has per-client tickets.",
            )
        if add_key.strip():
            updated_projects.append({
                "key": add_key.strip().upper(),
                "name": add_name.strip() or add_key.strip().upper(),
                "multi_client": add_mc,
                "client_extraction": "title_prefix" if add_mc else "none",
                "scope": team_scope.default_scope_dict(),
            })

    # ── Tab 3: Service Desk ─────────────────────────────────────────
    with tabs[2]:
        sd = ws.get("service_desk", {})
        sd_enabled = st.checkbox("Enable Service Desk", value=sd.get("enabled", False), key="_cfg_sd_en")

        if sd_enabled:
            st.markdown("### Service Desk Project")
            c1, c2 = st.columns(2)
            with c1:
                sd_key = st.text_input(
                    "Project Key",
                    value=sd.get("project_key", ""),
                    key="_cfg_sd_key",
                    help="Jira project key for change tickets (e.g. TCKT).",
                )
                sd_itid = st.text_input(
                    "Issue Type ID",
                    value=str(sd.get("issue_type_id", "")),
                    key="_cfg_sd_it",
                    help="Jira issue type ID for [System] Change tickets.",
                )
            with c2:
                sd_sdid = str(sd.get("service_desk_id", "") or "")
                sd_rtid = str(sd.get("request_type_id", "") or "")

            st.markdown("### Request Type Auto-Set")
            st.caption(
                "Required for **Service Ticket** — auto-assigns the portal Request Type after TCKT creation. "
                "Use **Fetch from Jira** below (recommended) or enter IDs manually."
            )

            fetch_col, _ = st.columns([1, 2])
            with fetch_col:
                if st.button("Fetch from Jira", key="_cfg_fetch_sd", type="secondary"):
                    try:
                        with st.spinner("Loading service desks from Jira…"):
                            st.session_state["_sd_lookup_desks"] = jira_client.list_service_desks()
                            st.session_state.pop("_sd_lookup_rts", None)
                    except jira_client.JiraApiError as exc:
                        st.error(str(exc))

            desks = st.session_state.get("_sd_lookup_desks", [])
            if desks:
                proj = (sd_key or sd.get("project_key", "TCKT")).strip().upper()
                default_desk_idx = 0
                for i, desk in enumerate(desks):
                    if str(desk.get("projectKey", "")).upper() == proj:
                        default_desk_idx = i
                        break

                desk_labels = [
                    f"{d.get('projectKey', '?')} — {d.get('projectName', 'Service Desk')} (desk ID {d.get('id')})"
                    for d in desks
                ]
                picked_desk_idx = st.selectbox(
                    "Service Desk",
                    options=list(range(len(desks))),
                    index=default_desk_idx,
                    format_func=lambda i: desk_labels[i],
                    key="_cfg_desk_pick_idx",
                )
                picked_desk = desks[picked_desk_idx]
                sd_sdid = str(picked_desk.get("id", ""))

                rt_cache_key = f"_sd_rts_{sd_sdid}"
                if rt_cache_key not in st.session_state:
                    try:
                        with st.spinner("Loading request types…"):
                            st.session_state[rt_cache_key] = jira_client.list_request_types(sd_sdid)
                    except jira_client.JiraApiError as exc:
                        st.error(str(exc))
                        st.session_state[rt_cache_key] = []

                request_types = st.session_state.get(rt_cache_key, [])
                if request_types:
                    rt_labels = [
                        f"{r.get('name', '?')} (type ID {r.get('id')})"
                        for r in request_types
                    ]
                    preferred_names = (
                        "submit a normal or emergency change",
                        "normal or emergency change",
                        "submit a standard change",
                        "change",
                    )
                    default_rt_idx = 0
                    for i, rt in enumerate(request_types):
                        name = str(rt.get("name", "")).lower()
                        if any(p in name for p in preferred_names):
                            default_rt_idx = i
                            break

                    picked_rt_idx = st.selectbox(
                        "Request Type",
                        options=list(range(len(request_types))),
                        index=default_rt_idx,
                        format_func=lambda i: rt_labels[i],
                        key="_cfg_rt_pick_idx",
                    )
                    sd_rtid = str(request_types[picked_rt_idx].get("id", ""))
                    st.success(
                        f"Ready to save: Service Desk ID **{esc(sd_sdid)}**, "
                        f"Request Type ID **{esc(sd_rtid)}**"
                    )
                else:
                    st.warning("No request types returned for this service desk.")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    sd_sdid = st.text_input(
                        "Service Desk ID",
                        value=sd_sdid,
                        key="_cfg_sd_sdid",
                        help="Numeric service desk ID, or click Fetch from Jira above.",
                    )
                with c2:
                    sd_rtid = st.text_input(
                        "Request Type ID",
                        value=sd_rtid,
                        key="_cfg_sd_rtid",
                        help="Numeric request type ID for your change type.",
                    )
                st.info("Click **Fetch from Jira** to load desks and request types automatically.")

            st.markdown("### Custom Field IDs")
            sd_fields = sd.get("fields", {})
            field_keys = [
                "change_type", "change_risk", "impact", "urgency",
                "planned_start", "planned_end", "implementation_plan",
                "test_plan", "backout_plan", "business_impact",
                "approvers", "approver_groups", "affected_services", "team",
            ]
            updated_fields = {}
            cols = st.columns(2)
            for i, fk in enumerate(field_keys):
                with cols[i % 2]:
                    updated_fields[fk] = st.text_input(
                        fk.replace("_", " ").title(),
                        value=sd_fields.get(fk, ""),
                        key=f"_cfg_sf_{fk}",
                    )

            st.markdown("### Defaults (JSON)")
            st.caption("Approvers, approver groups, change type IDs, etc. Edit as YAML/JSON.")
            sd_defaults = sd.get("defaults", {})
            defaults_yaml = yaml.dump(sd_defaults, default_flow_style=False) if sd_defaults else ""
            new_defaults_yaml = st.text_area(
                "Defaults YAML",
                value=defaults_yaml,
                height=250,
                key="_cfg_sd_defaults",
            )

    # ── Tab 4: Deployment ───────────────────────────────────────────
    with tabs[3]:
        dep = ws.get("deployment", {})
        st.markdown("### Deployment Settings")
        new_env = st.text_input(
            "Environment Name",
            value=dep.get("environment", "Production"),
            key="_cfg_dep_env",
            help="Target environment name used in deployment comments (e.g. Production, Staging).",
        )

    # ── Tab 5: Release Notes ────────────────────────────────────────
    with tabs[4]:
        rn = ws.get("release_notes", {})
        rn_enabled = st.checkbox("Enable Release Notes", value=rn.get("enabled", False), key="_cfg_rn_en")
        if rn_enabled:
            c1, c2 = st.columns(2)
            with c1:
                rn_team = st.text_input(
                    "Team Name",
                    value=rn.get("team_name", ""),
                    key="_cfg_rn_team",
                    help="Team name shown in the release notes document.",
                )
                rn_owner = st.text_input(
                    "Release Owner",
                    value=rn.get("release_owner", ""),
                    key="_cfg_rn_owner",
                    help="Person listed as release owner in the document.",
                )
                rn_smgr = st.text_input(
                    "Senior Manager",
                    value=rn.get("senior_mgr", ""),
                    key="_cfg_rn_smgr",
                    help="Senior manager approver name.",
                )
            with c2:
                rn_dir = st.text_input(
                    "Director",
                    value=rn.get("director", ""),
                    key="_cfg_rn_dir",
                    help="Director approver name.",
                )
                rn_svp = st.text_input(
                    "GM",
                    value=rn.get("svp", ""),
                    key="_cfg_rn_svp",
                    help="General Manager (GM) approver name.",
                )
                rn_gen = st.text_input(
                    "Generator Script Path",
                    value=rn.get("generator_script", ""),
                    key="_cfg_rn_gen",
                    help="Path to a custom generator script. Leave empty to use the built-in generator.",
                )

    # ── Tab 6: Apps ─────────────────────────────────────────────────
    with tabs[5]:
        st.markdown("### Enabled Apps")
        st.caption("Toggle which apps appear on the home page.")
        apps_cfg = ws.get("apps", {})
        all_app_ids = [
            "ticket_review",
            "release_notes",
            "service_ticket",
            "release_deployer",
            "ai_ticket_creator",
        ]
        _LABELS = {
            "ticket_review": "Ticket Review",
            "release_notes": "Release Notes",
            "service_ticket": "Service Ticket",
            "release_deployer": "Release Deployer",
            "ai_ticket_creator": "AI Ticket Creator",
        }
        updated_apps = {}
        for aid in all_app_ids:
            acfg = apps_cfg.get(aid, {})
            c1, c2 = st.columns([1, 3])
            with c1:
                enabled = st.checkbox(
                    _LABELS.get(aid, aid),
                    value=acfg.get("enabled", True),
                    key=f"_cfg_app_en_{aid}",
                )
            with c2:
                label = st.text_input(
                    "Label",
                    value=acfg.get("label", _LABELS.get(aid, "")),
                    key=f"_cfg_app_lbl_{aid}",
                    label_visibility="collapsed",
                )
            updated_apps[aid] = {"enabled": enabled, "label": label}

    # ── Tab 7: Integrations ───────────────────────────────────────────
    with tabs[6]:
        st.markdown("### Archived integrations")
        st.info(
            "Slack announce, Teams scheduling, and SharePoint Graph auto-upload are **archived**. "
            "Restore blocks from `archive/*.yaml` into `workspace.yaml` when IT is ready."
        )
        with st.expander("archive/slack_announce.yaml", expanded=False):
            st.caption("Deployment Slack bot announce — requires SLACK_BOT_TOKEN.")
        with st.expander("archive/teams_schedule.yaml", expanded=False):
            st.caption("Teams review/deployment meetings — requires MS_GRAPH_* + Calendars.ReadWrite.")
        with st.expander("archive/sharepoint_upload.yaml", expanded=False):
            st.caption("Graph PUT upload for Release Notes .docx — requires MS_GRAPH_* + Sites.ReadWrite.All.")

        st.markdown("### Release gates (Jira status checks)")
        gates_ws = ws.get("release_gates", {})
        import release_gates
        from slack_assignee_notify import gate_slack_status

        st.checkbox(
            "Release gates enabled",
            value=bool(gates_ws.get("enabled", True)),
            key="_cfg_gates_en",
            disabled=True,
            help="Edit release_gates in workspace.yaml (Settings export) to change statuses.",
        )
        pre = gates_ws.get("pre_review") or {}
        post = gates_ws.get("post_qa") or {}
        st.caption(
            f"Pre-review gate: {'on' if pre.get('enabled', False) else 'off (flag)'} · "
            f"Ticket Review UI: {'on' if pre.get('filter_ticket_review', False) else 'off'} · "
            f"Post-QA gate: {'on' if post.get('enabled', False) else 'off (flag)'} · "
            f"Release Notes UI: {'on' if post.get('filter_release_notes', False) else 'off'}"
        )
        with st.expander("Configured Jira statuses", expanded=False):
            st.markdown("**Pre-review ready:** " + ", ".join(release_gates.pre_review_statuses()))
            st.markdown("**Post-QA passed:** " + ", ".join(release_gates.qa_passed_statuses()))
        if not config.slack_archived():
            slack_gate = gate_slack_status()
            if slack_gate.get("can_dm_assignees"):
                st.success("SLACK_BOT_TOKEN ready for assignee DMs.")
            else:
                st.info("Assignee Slack DMs need SLACK_BOT_TOKEN (im:write, users:read.email).")
        st.caption(
            "Enable in workspace.yaml when production-ready: "
            "pre_review.enabled + filter_ticket_review · "
            "post_qa.enabled + filter_release_notes."
        )

        st.markdown("### Release Notes (E2E generator)")
        try:
            from generators.release_notes_e2e import e2e_status

            rn = e2e_status()
            if rn.get("ok"):
                st.success(
                    f"Fixture E2E passed — build **{esc(str(rn.get('generator_build_id', '')))}**, "
                    f"score **{rn.get('readiness_score')}/100**."
                )
            else:
                st.warning("Fixture E2E reported issues — run test script below.")
            with st.expander("Pipeline steps", expanded=False):
                for step in rn.get("pipeline_steps") or []:
                    icon = "✅" if step.get("ok") else "⬜"
                    st.markdown(f"{icon} {esc(step.get('label', ''))} — {esc(step.get('detail', ''))}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not load release notes E2E status: {exc}")
        st.caption("CLI: python orchestrator/zones/platform/ops/test_release_notes_e2e.py")

        if config.teams_archived():
            st.caption("Teams scheduling is archived — see `archive/teams_schedule.yaml`.")
        else:
            st.markdown("### Teams meeting scheduling")
            ts_enabled = st.checkbox(
                "Enable Teams scheduling",
                value=bool(teams_ws.get("enabled", False)),
                key="_cfg_ts_en",
            )
            ts_org = st.text_input(
                "Organizer mailbox (UPN)",
                value=teams_ws.get("organizer_upn", ""),
                key="_cfg_ts_org",
                help="Calendar owner — usually your @abcfitness.com email.",
            )
            c_ts1, c_ts2, c_ts3 = st.columns(3)
            with c_ts1:
                ts_tz = st.text_input(
                    "Timezone",
                    value=teams_ws.get("default_timezone", "Asia/Kolkata"),
                    key="_cfg_ts_tz",
                )
            with c_ts2:
                ts_review_min = st.number_input(
                    "Review duration (min)",
                    min_value=15,
                    max_value=480,
                    value=int(teams_ws.get("review_duration_minutes") or 45),
                    key="_cfg_ts_review_min",
                )
            with c_ts3:
                ts_deploy_min = st.number_input(
                    "Deployment duration (min)",
                    min_value=15,
                    max_value=480,
                    value=int(teams_ws.get("deployment_duration_minutes") or 180),
                    key="_cfg_ts_deploy_min",
                )

            existing_attendees = teams_ws.get("default_attendees") or []
            attendee_lines = []
            for item in existing_attendees:
                if isinstance(item, dict):
                    email = str(item.get("email") or "").strip()
                    name = str(item.get("name") or "").strip()
                    attendee_lines.append(f"{email}, {name}" if name else email)
                elif isinstance(item, str):
                    attendee_lines.append(item.strip())
            ts_attendees_raw = st.text_area(
                "Default attendees (one per line: email, optional name)",
                value="\n".join(attendee_lines),
                height=120,
                key="_cfg_ts_attendees",
            )

            live_cfg = teams_schedule.load_schedule_config({
                **teams_ws,
                "enabled": ts_enabled,
                "organizer_upn": ts_org,
            })
            for step in teams_schedule.readiness_steps(live_cfg):
                icon = "✅" if step.get("ok") else "⬜"
                st.markdown(f"{icon} {esc(step.get('label', ''))} — {esc(step.get('detail', ''))}")

            if st.button("Test Teams preview (dry-run)", key="_cfg_ts_preview"):
                draft = teams_schedule.build_meeting_draft(
                    live_cfg,
                    kind="review",
                    subject="Release Orchestrator setup test",
                    start=__import__("datetime").datetime.now().replace(second=0, microsecond=0),
                    version="setup-test",
                )
                preview = teams_schedule.schedule_meeting(live_cfg, draft, dry_run=True)
                if preview.ok:
                    st.success("Dry-run preview OK — Graph payload is valid.")
                    st.code(json.dumps(preview.graph_payload or {}, indent=2), language="json")
                else:
                    st.error(preview.error or "Preview failed.")

    # ── Save / Export ───────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("\U0001f4be Save Configuration", type="primary", use_container_width=True, key="_cfg_save"):
            project_errors = validate_workspace_projects(updated_projects)
            if project_errors:
                for err in project_errors:
                    st.error(err)
            else:
                new_ws = dict(ws)
                new_ws.update({
                    "name": new_name,
                    "jira": {"base_url": new_url or ws.get("jira", {}).get("base_url", "")},
                    "projects": updated_projects,
                    "service_desk": _build_sd_config(
                        sd_enabled, ws, locals()
                    ),
                    "deployment": {"environment": new_env},
                    "release_notes": _build_rn_config(rn_enabled if 'rn_enabled' in dir() else False, ws, locals()),
                    "teams_schedule": _build_teams_config(ws, locals()),
                    "apps": updated_apps,
                })
                _save_raw(new_ws)
                config.ensure_workspace_loaded(force=True)

                if new_email.strip() or new_token.strip():
                    save_and_reload_env(
                        new_email.strip() or config.JIRA_EMAIL,
                        new_token.strip() or config.JIRA_API_TOKEN,
                        new_url or None,
                    )

                st.success("Configuration saved! Reloading...")
                st.rerun()

    with c2:
        if st.button("\U0001f3e0 Back to Home", use_container_width=True, key="_cfg_home"):
            _go_home()

    with c3:
        with st.expander("Export / Import", expanded=False):
            ws_file = _ws_path()
            st.download_button(
                "Download workspace.yaml",
                data=open(ws_file, "r", encoding="utf-8").read() if os.path.exists(ws_file) else "",
                file_name="workspace.yaml",
                mime="text/yaml",
                key="_cfg_export",
            )
            uploaded = st.file_uploader("Import workspace.yaml", type=["yaml", "yml"], key="_cfg_import")
            pending = st.session_state.get("_cfg_import_pending")
            if uploaded and not pending:
                st.session_state["_cfg_import_pending"] = uploaded.read().decode("utf-8")
                st.rerun()
            if pending:
                st.warning("Import will overwrite your current workspace configuration.")
                c_imp1, c_imp2 = st.columns(2)
                with c_imp1:
                    if st.button("Confirm import", key="_cfg_import_confirm"):
                        with open(ws_file, "w", encoding="utf-8") as f:
                            f.write(pending)
                        st.session_state.pop("_cfg_import_pending", None)
                        config.ensure_workspace_loaded(force=True)
                        st.success("Imported! Reloading...")
                        st.rerun()
                with c_imp2:
                    if st.button("Cancel import", key="_cfg_import_cancel"):
                        st.session_state.pop("_cfg_import_pending", None)
                        st.rerun()


def _build_sd_config(enabled: bool, ws: dict, loc: dict) -> dict:
    sd = ws.get("service_desk", {})
    if not enabled:
        preserved = dict(sd)
        preserved["enabled"] = False
        return preserved
    result = {
        "enabled": True,
        "project_key": loc.get("sd_key", sd.get("project_key", "")),
        "issue_type_id": loc.get("sd_itid", str(sd.get("issue_type_id", ""))),
        "service_desk_id": loc.get("sd_sdid", str(sd.get("service_desk_id", ""))),
        "request_type_id": loc.get("sd_rtid", str(sd.get("request_type_id", ""))),
    }
    if "updated_fields" in loc:
        result["fields"] = loc["updated_fields"]
    else:
        result["fields"] = sd.get("fields", {})

    if "new_defaults_yaml" in loc and loc["new_defaults_yaml"].strip():
        try:
            result["defaults"] = yaml.safe_load(loc["new_defaults_yaml"])
        except yaml.YAMLError as exc:
            st.error(f"Service Desk defaults YAML is invalid: {exc}")
            result["defaults"] = sd.get("defaults", {})
    else:
        result["defaults"] = sd.get("defaults", {})

    return result


def _build_teams_config(ws: dict, loc: dict) -> dict:
    """Persist teams_schedule block from Settings → Integrations tab."""
    prior = dict(ws.get("teams_schedule") or {})
    if "ts_enabled" not in loc:
        return prior
    raw = str(loc.get("ts_attendees_raw") or "").strip()
    attendees: list[dict[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "," in line:
            email, _, name = line.partition(",")
            entry: dict[str, str] = {"email": email.strip()}
            if name.strip():
                entry["name"] = name.strip()
            attendees.append(entry)
        else:
            attendees.append({"email": line})
    return {
        **prior,
        "enabled": bool(loc.get("ts_enabled")),
        "organizer_upn": str(loc.get("ts_org") or "").strip(),
        "default_timezone": str(loc.get("ts_tz") or "Asia/Kolkata").strip() or "Asia/Kolkata",
        "review_duration_minutes": int(loc.get("ts_review_min") or 45),
        "deployment_duration_minutes": int(loc.get("ts_deploy_min") or 180),
        "default_attendees": attendees,
        "review_attendees": prior.get("review_attendees") or [],
        "deployment_attendees": prior.get("deployment_attendees") or [],
    }


def _build_rn_config(enabled: bool, ws: dict, loc: dict) -> dict:
    rn = ws.get("release_notes", {})
    if not enabled:
        preserved = dict(rn)
        preserved["enabled"] = False
        return preserved
    return {
        "enabled": True,
        "team_name": loc.get("rn_team", rn.get("team_name", "")),
        "release_owner": loc.get("rn_owner", rn.get("release_owner", "")),
        "senior_mgr": loc.get("rn_smgr", rn.get("senior_mgr", "")),
        "director": loc.get("rn_dir", rn.get("director", "")),
        "svp": loc.get("rn_svp", rn.get("svp", "")),
        "generator_script": loc.get("rn_gen", rn.get("generator_script", "")),
    }
