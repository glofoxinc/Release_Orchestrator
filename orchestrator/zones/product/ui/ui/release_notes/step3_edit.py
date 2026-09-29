"""Step 3 — Edit all release notes content before generation."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

import config
import jira_client
import release_gates
from generators.release_notes_deployment import (
    build_deployment_rows,
    enrich_deployment_rows,
    format_deployment_rows,
    merge_parsed_deployments,
    parse_deployment_rows,
)
from generators.release_notes_insights import (
    build_release_summary_paragraph,
    is_generic_release_summary,
)
from generators.release_notes_summary_tables import build_highlight_summary_tables
from generators.release_notes_quality import (
    assess_release_notes_quality,
    build_custom_clients_list,
    prepare_change_table_entries,
)
from generators.release_notes_report_tables import (
    build_analyze_report_rows,
    build_custom_client_report_tables,
    build_delivered_reports_rows,
    format_analyze_report_rows,
    format_custom_client_report_tables,
)
from generators.release_notes_template_defaults import (
    build_testing_evidence_editor_text,
    build_testing_evidence_ticket_lines,
)
from release_platform.ui.helpers import (
    clear_release_doc_version_metadata,
    collect_release_notes_deploy_info,
    derive_release_doc_metadata,
    esc,
    mark_release_doc_metadata_customized,
    release_doc_metadata_fallback_today,
    release_notes_uses_fix_version,
    release_selection_fingerprint,
    resolve_rn_extracted_from_state,
    ss_default,
    sync_release_doc_metadata,
)
from release_platform.ui.release_notes.readiness_panel import render_release_notes_readiness
from release_platform.ui.workflow import render_action_hint


def _go(step: int) -> None:
    from session_persist import persist_session

    persist_session(dict(st.session_state))
    st.session_state["rn_step"] = step
    st.rerun()


def _selected_release_names() -> list[str]:
    names: list[str] = []
    for proj in config.PROJECTS:
        rel = st.session_state.get(f"rn_release_{proj['key']}", {})
        if rel.get("name"):
            names.append(str(rel["name"]))
    return names


def _release_version_name() -> str:
    names = _selected_release_names()
    return " + ".join(names) if names else ""


def _client_owners_from_extracted(extracted: list[dict]) -> dict[str, str]:
    from generators.release_notes_quality import canonical_client_name, improve_extracted

    owners: dict[str, str] = {}
    for entry in improve_extracted(extracted):
        if entry.get("type") == "Analyze":
            label = "Analyze"
        else:
            label = canonical_client_name(entry.get("client") or "") or entry.get("client") or "Custom"
        if label not in owners:
            owners[label] = entry.get("assignee", "")
    return owners


def _build_change_rows_text(extracted: list[dict]) -> str:
    """Build pipe-delimited Ticket Details rows with quality repairs applied."""
    from generators.release_notes_generator import format_change_row
    from generators.release_notes_test_by import (
        assign_change_table_testers,
        assign_change_table_testing_statuses,
    )

    release_seed = _release_version_name()
    test_by_names = assign_change_table_testers(extracted, release_seed=release_seed)
    testing_statuses = assign_change_table_testing_statuses(extracted)
    rows = []
    for entry in prepare_change_table_entries(
        extracted,
        test_by_names=test_by_names,
        testing_statuses=testing_statuses,
    ):
        rows.append(
            format_change_row(
                sno=entry["sno"],
                ticket=entry["ticket"],
                parent_epic=entry["parent_epic"],
                link=entry["link"],
                type_=entry["type"],
                client=entry["client"],
                report=entry["report"],
                description=entry["description"],
                assignee=entry.get("assignee") or "",
                test_by=entry["test_by"],
                comments=entry.get("comments") or "",
                testing_status=entry.get("testing_status") or "",
            )
        )
    return "\n".join(rows)


def _rebuild_quality_sections(*, include_change_rows: bool = True) -> None:
    """Re-apply quality pipeline to highlights, report tables, clients, and change rows."""
    extracted = st.session_state.get("rn_extracted", [])
    st.session_state["rn_summary_p2"] = ""
    st.session_state["rn_analyze_report_rows"] = format_analyze_report_rows(
        build_analyze_report_rows(extracted),
    )
    st.session_state["rn_custom_report_tables"] = format_custom_client_report_tables(
        build_custom_client_report_tables(extracted),
    )
    st.session_state["rn_delivered_report_rows"] = "\n".join(
        "|".join(row) for row in build_delivered_reports_rows(extracted)
    )
    st.session_state["rn_custom_clients"] = ", ".join(build_custom_clients_list(extracted))
    if extracted:
        st.session_state["rn_summary_p1"] = build_release_summary_paragraph(extracted)
    if include_change_rows:
        st.session_state["rn_change_rows"] = _build_change_rows_text(extracted)
        deployment_rows = st.session_state.get("rn_deployment_rows", "")
        evidence_text = build_testing_evidence_editor_text(
            extracted,
            deployment_rows=deployment_rows,
        )
        st.session_state["rn_screenshot_names"] = evidence_text
        st.session_state["rn_testing_evidence_tickets"] = evidence_text
    if not (st.session_state.get("rn_deployment_rows") or "").strip():
        owners = _client_owners_from_extracted(extracted)
        deploy_info = collect_release_notes_deploy_info(_release_version_name())
        st.session_state["rn_deployment_rows"] = build_deployment_rows(owners, deploy_info or {})
    else:
        _apply_deployment_enrichment(overwrite=False)


def _apply_deployment_enrichment(*, overwrite: bool = False) -> None:
    deploy_info = collect_release_notes_deploy_info(_release_version_name())
    if not deploy_info:
        return
    rows = parse_deployment_rows(st.session_state.get("rn_deployment_rows", ""))
    if not rows:
        rows = [
            [client, owner, "", ""]
            for client, owner in sorted(_client_owners_from_extracted(
                st.session_state.get("rn_extracted", [])
            ).items())
        ]
    enriched = enrich_deployment_rows(rows, deploy_info, overwrite=overwrite)
    st.session_state["rn_deployment_rows"] = format_deployment_rows(enriched)


def _field_empty(key: str) -> bool:
    return not str(st.session_state.get(key) or "").strip()


def _defaults_fingerprint(extracted: list) -> str:
    import hashlib
    import json

    snap = st.session_state.get("shared_snapshot") or {}
    payload = {
        "count": len(extracted),
        "keys": sorted(str(t.get("key", "")) for t in extracted[:100]),
        "version": _release_version_name(),
        "excluded": sorted(snap.get("excluded_keys") or []),
        "qa_excluded": sorted(snap.get("qa_excluded_keys") or []),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _build_defaults() -> None:
    """Populate editable fields from extracted ticket data + config defaults."""
    extracted = st.session_state.get("rn_extracted", [])
    fp = _defaults_fingerprint(extracted)
    if st.session_state.get("_rn_defaults_fp") == fp:
        return
    meta = config.RELEASE_META

    sync_release_doc_metadata("rn_")

    ss_default("rn_dev_team", meta["dev_team"])
    ss_default("rn_release_owner", meta["release_owner"])
    ss_default("rn_senior_mgr", meta["senior_mgr"])
    ss_default("rn_director", meta["director"])
    ss_default("rn_svp", meta["svp"])
    ss_default("rn_environment", meta["environment"])

    if "rn_summary_p1" not in st.session_state:
        st.session_state["rn_summary_p1"] = build_release_summary_paragraph(extracted)
    elif extracted and is_generic_release_summary(st.session_state.get("rn_summary_p1", "")):
        st.session_state["rn_summary_p1"] = build_release_summary_paragraph(extracted)

    if "rn_summary_p2" not in st.session_state:
        st.session_state["rn_summary_p2"] = ""

    if "rn_analyze_report_rows" not in st.session_state or _field_empty("rn_analyze_report_rows"):
        st.session_state["rn_analyze_report_rows"] = format_analyze_report_rows(
            build_analyze_report_rows(extracted),
        )

    if "rn_custom_report_tables" not in st.session_state:
        st.session_state["rn_custom_report_tables"] = format_custom_client_report_tables(
            build_custom_client_report_tables(extracted),
        )

    if "rn_custom_clients" not in st.session_state:
        st.session_state["rn_custom_clients"] = ", ".join(build_custom_clients_list(extracted))

    if "rn_change_rows" not in st.session_state or _field_empty("rn_change_rows"):
        st.session_state["rn_change_rows"] = _build_change_rows_text(extracted) if extracted else ""

    if "rn_deployment_rows" not in st.session_state:
        owners = _client_owners_from_extracted(extracted)
        deploy_info = collect_release_notes_deploy_info(_release_version_name())
        st.session_state["rn_deployment_rows"] = build_deployment_rows(owners, deploy_info)

    if "rn_delivered_report_rows" not in st.session_state:
        st.session_state["rn_delivered_report_rows"] = "\n".join(
            "|".join(row) for row in build_delivered_reports_rows(extracted)
        )

    if "rn_testing_evidence_tickets" not in st.session_state or _field_empty("rn_testing_evidence_tickets"):
        evidence_text = build_testing_evidence_editor_text(
            extracted,
            deployment_rows=st.session_state.get("rn_deployment_rows", ""),
        )
        st.session_state["rn_testing_evidence_tickets"] = evidence_text
        st.session_state["rn_screenshot_names"] = evidence_text

    if "rn_screenshot_names" not in st.session_state or _field_empty("rn_screenshot_names"):
        st.session_state["rn_screenshot_names"] = build_testing_evidence_editor_text(
            extracted,
            deployment_rows=st.session_state.get("rn_deployment_rows", ""),
        )

    ss_default("rn_excluded_tickets", "")
    snap = st.session_state.get("shared_snapshot") or {}
    qa_excluded = snap.get("qa_excluded_keys") or []
    review_excluded = snap.get("excluded_keys") or []
    seed_keys = sorted(set(qa_excluded) | set(review_excluded))
    if seed_keys and not st.session_state.get("rn_excluded_tickets"):
        placeholders = [
            release_gates.GateTicket(
                key=k,
                summary="",
                status="",
                assignee_name="",
                assignee_email="",
                project=k.split("-")[0] if "-" in k else "",
                reason="Excluded during Ticket Review / QA gate",
            )
            for k in seed_keys
        ]
        st.session_state["rn_excluded_tickets"] = release_gates.format_excluded_table_text(
            placeholders,
        )
    ss_default("rn_notes", "")
    st.session_state["_rn_defaults_fp"] = fp


def ensure_release_notes_draft() -> None:
    """Fill missing version, tables, and metadata — safe before Step 4 generate."""
    extracted = resolve_rn_extracted_from_state(st.session_state)
    if extracted:
        st.session_state["rn_extracted"] = extracted
    elif not (st.session_state.get("rn_change_rows") or "").strip():
        return

    meta = config.RELEASE_META

    if release_notes_uses_fix_version("rn_"):
        if _field_empty("rn_version"):
            st.session_state.pop("rn_metadata_customized", None)
        sync_release_doc_metadata("rn_")
        if _field_empty("rn_version"):
            version, doc_date = derive_release_doc_metadata("rn_")
            if not version:
                version, doc_date = release_doc_metadata_fallback_today()
            st.session_state["rn_version"] = version
            st.session_state["rn_date"] = doc_date
            st.session_state.pop("_rn_ver", None)
            st.session_state.pop("_rn_dt", None)
    else:
        if _field_empty("rn_version"):
            deploy_on = st.session_state.get("stk_planned_start_date")
            version, doc_date = release_doc_metadata_fallback_today(
                on=deploy_on if isinstance(deploy_on, date) else None,
            )
            st.session_state["rn_version"] = version
            st.session_state["rn_date"] = doc_date
            st.session_state.pop("_rn_ver", None)
            st.session_state.pop("_rn_dt", None)

    if extracted:
        _build_defaults()

        needs_rebuild = (
            _field_empty("rn_change_rows")
            or _field_empty("rn_analyze_report_rows")
            or _field_empty("rn_summary_p1")
            or _field_empty("rn_testing_evidence_tickets")
        )
        if needs_rebuild:
            _rebuild_quality_sections(include_change_rows=True)

        if _field_empty("rn_delivered_report_rows"):
            st.session_state["rn_delivered_report_rows"] = "\n".join(
                "|".join(row) for row in build_delivered_reports_rows(extracted)
            )

    if _field_empty("rn_dev_team"):
        st.session_state["rn_dev_team"] = meta["dev_team"]
    if _field_empty("rn_release_owner"):
        st.session_state["rn_release_owner"] = meta["release_owner"]


def render() -> None:
    st.markdown("## Edit Release Notes Content")

    if st.session_state.get("rn_extracted"):
        ensure_release_notes_draft()

    if st.session_state.pop("_rn_pending_meta_reset", False):
        sync_release_doc_metadata("rn_")
        st.rerun()

    extracted = st.session_state.get("rn_extracted") or []
    if not extracted:
        st.warning(
            "No tickets loaded for editing. Go back to **Step 2** and select at least one ticket."
        )
        if st.button("\u2190 Back to ticket selection", key="rn_s3_empty_back"):
            _go(2)
        return

    st.markdown("All fields are pre-filled from tickets. Edit as needed before generating.")

    _build_defaults()

    rows = parse_deployment_rows(st.session_state.get("rn_deployment_rows", ""))
    if rows and any(not row[2].strip() or not row[3].strip() for row in rows):
        _apply_deployment_enrichment(overwrite=False)

    uses_fix_version = release_notes_uses_fix_version("rn_")
    release_names = _selected_release_names() if uses_fix_version else []
    if release_names:
        version, doc_date = derive_release_doc_metadata("rn_")
        st.caption(
            f"Version and date are auto-filled from fix version "
            f"**{' + '.join(release_names)}** → `{esc(version)}`, `{esc(doc_date)}`. "
            "Edit below if needed."
        )
    elif not uses_fix_version:
        deploy_on = st.session_state.get("stk_planned_start_date")
        auto_version, auto_date = release_doc_metadata_fallback_today(
            on=deploy_on if isinstance(deploy_on, date) else None,
        )
        st.caption(
            "Tickets were loaded **by status** — version and release date default from the "
            f"planned deploy date (`{esc(auto_version)}`, `{esc(auto_date)}`). Edit below if needed."
        )

    derived_version, derived_date = (
        derive_release_doc_metadata("rn_")
        if uses_fix_version
        else release_doc_metadata_fallback_today(
            on=st.session_state.get("stk_planned_start_date")
            if isinstance(st.session_state.get("stk_planned_start_date"), date)
            else None,
        )
    )

    st.markdown("### Metadata")
    c1, c2 = st.columns(2)
    with c1:
        if uses_fix_version:
            st.text_input(
                "Version",
                key="rn_version",
                placeholder="v2026.3.07.08",
                help="Release version from the Jira fix version (Q = middle segment: .3. = Q3).",
            )
            st.text_input(
                "Release Date",
                key="rn_date",
                placeholder="08-July-2026",
                help="Date parsed from fix version name (day-month-year), not today's calendar date.",
            )
            if (
                derived_version
                and (
                    st.session_state.get("rn_version", "") != derived_version
                    or st.session_state.get("rn_date", "") != derived_date
                )
            ):
                mark_release_doc_metadata_customized("rn_")
            if derived_version and st.button("Reset version/date from fix version", key="rn_reset_meta"):
                st.session_state["rn_metadata_customized"] = False
                st.session_state.pop("rn_version", None)
                st.session_state.pop("rn_date", None)
                st.session_state.pop("_rn_ver", None)
                st.session_state.pop("_rn_dt", None)
                st.session_state["_rn_pending_meta_reset"] = True
                st.rerun()
        st.session_state["rn_dev_team"] = st.text_input(
            "Dev Team",
            value=st.session_state["rn_dev_team"],
            key="_rn_team",
            placeholder="Customize BI Team",
            help="Team name shown in the metadata table.",
        )
        st.session_state["rn_release_owner"] = st.text_input(
            "Release Owner",
            value=st.session_state["rn_release_owner"],
            key="_rn_owner",
            placeholder="Full Name",
            help="Person responsible for this release.",
        )
    with c2:
        st.session_state["rn_senior_mgr"] = st.text_input(
            "Senior Manager",
            value=st.session_state["rn_senior_mgr"],
            key="_rn_smgr",
            placeholder="Full Name",
            help="Senior manager approver.",
        )
        st.session_state["rn_director"] = st.text_input(
            "Director",
            value=st.session_state["rn_director"],
            key="_rn_dir",
            placeholder="Full Name",
            help="Director approver.",
        )
        st.session_state["rn_svp"] = st.text_input(
            "GM",
            value=st.session_state["rn_svp"],
            key="_rn_svp",
            placeholder="Full Name",
            help="General Manager (GM) approver.",
        )
        st.session_state["rn_environment"] = st.text_input(
            "Environment",
            value=st.session_state["rn_environment"],
            key="_rn_env",
            placeholder="Production",
            help="Target deployment environment.",
        )

    st.markdown("### Release Summary")
    st.session_state["rn_summary_p1"] = st.text_area(
        "Summary paragraph",
        value=st.session_state["rn_summary_p1"],
        height=80,
        key="_rn_sp1",
        help="Opening paragraph after the 'Release Summary' heading in the Word document.",
    )
    st.markdown("### Key Highlights")
    st.caption(
        "Category counts by New Reports, Customizations, Looker Exits, and Optimizations."
    )
    extracted = st.session_state.get("rn_extracted", [])
    highlight_blocks = build_highlight_summary_tables(extracted)
    if highlight_blocks:
        for block in highlight_blocks:
            st.markdown(f"**{block.title}**")
            st.dataframe(
                pd.DataFrame(block.rows, columns=list(block.headers)),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("Select tickets in Step 2 to populate Key Highlights summary tables.")
    rebuild_cols = st.columns([1, 1, 2])
    with rebuild_cols[0]:
        if st.button("Rebuild release content", key="rn_rebuild_quality"):
            _rebuild_quality_sections(include_change_rows=True)
            st.rerun()
    with rebuild_cols[1]:
        st.caption(
            "Re-applies category summary, delivered reports, Ticket Details, "
            "and Testing Evidence ticket list."
        )
    quality_warnings = assess_release_notes_quality(
        highlight_lines=[],
        dashboard_lines=[],
        analyze_clients="",
        custom_clients=st.session_state.get("rn_custom_clients", ""),
    )
    if quality_warnings:
        with st.expander(f"Release notes quality checks ({len(quality_warnings)})", expanded=True):
            for warning in quality_warnings:
                st.warning(warning)

    st.markdown("### Reports / Dashboards Delivered")
    st.caption(
        "Single combined table: Client | Dashboard / Report | Change. "
        "Standard scope uses **Glofox Analyze** as the client name."
    )
    st.session_state["rn_delivered_report_rows"] = st.text_area(
        "Delivered reports",
        value=st.session_state.get("rn_delivered_report_rows", ""),
        height=180,
        key="_rn_delivered",
        help="One row per line: Client|Dashboard / Report|Change",
    )
    st.session_state["rn_custom_clients"] = st.text_input(
        "Custom clients (comma-separated, reference only)",
        value=st.session_state["rn_custom_clients"],
        key="_rn_cc",
        help="Used for deployment tracking owner labels; not shown as a separate Word section.",
    )

    with st.expander("Advanced: legacy report inventory rows (optional fallback)", expanded=False):
        st.caption(
            "Only used when delivered rows are empty. Prefer editing **Delivered reports** above."
        )
        st.session_state["rn_analyze_report_rows"] = st.text_area(
            "Analyze dashboards / paginated reports",
            value=st.session_state.get("rn_analyze_report_rows", ""),
            height=120,
            key="_rn_analyze_rows",
            help="Client|Report|Ticket#|Owner|Type|Label",
        )
        st.session_state["rn_custom_report_tables"] = st.text_area(
            "Custom client report tables",
            value=st.session_state.get("rn_custom_report_tables", ""),
            height=160,
            key="_rn_custom_tables",
            help="[ClientName] section headers, then pipe rows.",
        )

    st.markdown("### Deployment Tracking")
    st.caption(
        "Status and Deployment ID & Time auto-fill from the Release Deployer or deployment "
        "history when available. Paste deployment output below or edit rows manually."
    )

    paste_raw = st.text_area(
        "Paste deployment IDs (optional)",
        key="rn_paste_deploy",
        height=100,
        placeholder=(
            "Jetts Deployment ID: a4438257-1820-44e0-8639-efb05911871f\n"
            "14/04/26, 10:39"
        ),
        help="Paste CI/CD deployment output — client, UUID, date, and time are auto-detected.",
    )
    prev_paste = st.session_state.get("_rn_prev_paste_deploy", "")
    if paste_raw.strip() and paste_raw.strip() != prev_paste:
        st.session_state["_rn_prev_paste_deploy"] = paste_raw.strip()
        parsed = jira_client.parse_deployment_input(paste_raw)
        rows = parse_deployment_rows(st.session_state.get("rn_deployment_rows", ""))
        if not rows:
            rows = [
                [client, owner, "", ""]
                for client, owner in sorted(_client_owners_from_extracted(
                    st.session_state.get("rn_extracted", [])
                ).items())
            ]
        merged = merge_parsed_deployments(rows, parsed)
        st.session_state["rn_deployment_rows"] = format_deployment_rows(merged)

    fill_col, _ = st.columns([1, 3])
    with fill_col:
        if st.button("Fill from Deployer / History", key="rn_fill_deploy"):
            _apply_deployment_enrichment(overwrite=False)
            st.rerun()

    st.session_state["rn_deployment_rows"] = st.text_area(
        "Deployment rows",
        value=st.session_state["rn_deployment_rows"],
        height=100,
        key="_rn_deploy",
        help=(
            "One row per line: Client|Deployment Owner|Status|Deployment ID & Time "
            "(use '; ' between ID and date/time)"
        ),
    )

    st.markdown("### Ticket Details Table")
    st.caption(
        "**Test** is auto-filled evenly from the QA pool "
        "(Rekha, Mona, Navya, Chanti, Narasimha, Nikhath, Bharathi, Soumya, Sushma) — "
        "never the ticket owner (Jira assignee). "
        "**ETL tickets** (Mona-owned or 'BI Reporting'-type changes) → "
        "Test *Mona/Nikhila* and Status *ETL Done*; "
        "all others → *Done*."
    )
    rebuild_col, _ = st.columns([1, 3])
    with rebuild_col:
        if st.button("Rebuild Ticket Details", key="rn_rebuild_test_by"):
            st.session_state["rn_change_rows"] = _build_change_rows_text(
                st.session_state.get("rn_extracted", [])
            )
            st.rerun()
    st.caption(
        "Rebuilds ticket links, rebalances Test across the QA pool, and sets Status "
        "(ETL tickets → Mona/Nikhila + ETL Done; everyone else → Done)."
    )
    st.session_state["rn_change_rows"] = st.text_area(
        "Ticket detail rows",
        value=st.session_state["rn_change_rows"],
        height=250,
        key="_rn_cr",
        help=(
            "One row per line, pipe-delimited (5 columns): "
            "Ticket|Ticket Link|Assignee|Test|Status. "
            "Legacy 4- and 10-column rows are still accepted on import."
        ),
    )

    with st.expander("Post-deploy sections (Testing Evidence, Excluded, Notes)", expanded=True):
        st.session_state["rn_testing_evidence_tickets"] = st.text_area(
            "Testing Evidence (clients + ticket list)",
            value=st.session_state.get(
                "rn_testing_evidence_tickets",
                st.session_state.get("rn_screenshot_names", ""),
            ),
            height=220,
            key="_rn_testing_evidence",
            help=(
                "Lists all clients (for deployment/configuration screenshots) and each "
                "included ticket (for testing screenshots). The DOCX adds placeholder "
                "lines under each client and ticket for testers to paste images."
            ),
        )
        st.session_state["rn_screenshot_names"] = st.session_state["rn_testing_evidence_tickets"]
        st.session_state["rn_excluded_tickets"] = st.text_area(
            "Tickets excluded from deployment",
            value=st.session_state["rn_excluded_tickets"],
            height=60,
            key="_rn_excl",
            help="Optional lines listing excluded tickets.",
        )
        st.session_state["rn_notes"] = st.text_area(
            "Notes",
            value=st.session_state["rn_notes"],
            height=60,
            key="_rn_notes",
            help="Optional notes at the end of the document.",
        )

    st.markdown("### Release Notes Readiness")
    render_release_notes_readiness(st.session_state, show_apply_summary=True)

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Back", key="rn_s3_back"):
            _go(2)
    with c2:
        if st.button("Preview & Generate \u2192", type="primary", key="rn_s3_next"):
            st.session_state["rn_release_fp"] = release_selection_fingerprint("rn_")
            _go(4)
        render_action_hint(
            "Opens preview and .docx download. You will upload to SharePoint on the next step."
        )
