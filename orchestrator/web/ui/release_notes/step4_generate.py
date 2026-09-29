"""Step 4 — Preview release notes and generate .docx via built-in or external generator."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import pandas as pd
import streamlit as st

import config
import sharepoint_upload
from generators.release_notes_template_defaults import (
    CHANGE_HEADERS,
    DELIVERED_REPORTS_HEADERS,
    DEPLOYMENT_HEADERS,
    EXCLUDED_HEADERS,
    TESTING_EVIDENCE_HEADING,
    TESTING_EVIDENCE_SUBHEADING,
)
from generators.release_notes_report_tables import (
    parse_analyze_report_rows,
    parse_custom_client_report_tables,
)
from generators.release_notes_summary_tables import build_highlight_summary_tables
from release_platform.ui.release_notes.readiness_panel import (
    assess_readiness_cached,
    render_release_notes_e2e_checklist,
    render_release_notes_readiness,
)
from release_platform.ui.release_notes.step3_edit import ensure_release_notes_draft
from release_platform.ui.helpers import (
    build_rn_readiness_payload,
    derive_release_doc_metadata,
    esc,
    navigate_to_app,
    persist_rn_readiness_payload,
    release_notes_doc_filename,
    release_notes_uses_fix_version,
    sync_release_doc_metadata,
)
from release_platform.ui.workflow import (
    check_app_prerequisites,
    mark_release_doc_generated,
    render_action_hint,
    save_sharepoint_url,
    validate_sharepoint_url,
)


def _go(step: int) -> None:
    from session_persist import persist_session

    persist_session(dict(st.session_state))
    st.session_state["rn_step"] = step
    st.rerun()


def _parse_dashboard_items(raw: str) -> list[tuple[str, str]]:
    items = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" - ", 1)
        if len(parts) == 2:
            items.append((parts[0].strip(), " - " + parts[1].strip()))
        else:
            items.append((line, ""))
    return items


def _parse_change_rows(raw: str) -> list[list[str]]:
    from generators.parsing import parse_change_rows

    return parse_change_rows(raw)


_LEGACY_ENGINE_MARKER = "ENGINE \u2014 DO NOT EDIT BELOW"


def _script_has_legacy_engine(path: str) -> bool:
    """True when the configured script uses the legacy subprocess engine block."""
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            return _LEGACY_ENGINE_MARKER in f.read()
    except OSError:
        return False


def _has_external_generator() -> bool:
    """Use subprocess mode only for legacy scripts that include the engine marker."""
    rn_cfg = config._ws.get("release_notes", {})
    script = rn_cfg.get("generator_script", "")
    if not script:
        return False
    path = config.RELEASE_NOTES_GENERATOR
    return os.path.isfile(path) and _script_has_legacy_engine(path)


def _has_external_generator_cached() -> bool:
    ws_fp = config._workspace_reload_fingerprint()  # noqa: SLF001
    cache = st.session_state.get("_rn_external_generator_cache")
    if isinstance(cache, dict) and cache.get("ws_fp") == ws_fp:
        return bool(cache.get("value"))
    value = _has_external_generator()
    st.session_state["_rn_external_generator_cache"] = {"ws_fp": ws_fp, "value": value}
    return value


def _build_data_dict(ss: dict) -> dict:
    """Assemble a data dict from session state for the built-in generator."""
    uses_fix_version = release_notes_uses_fix_version("rn_")
    return {
        "version": ss.get("rn_version", "") if uses_fix_version else "",
        "release_date": ss.get("rn_date", "") if uses_fix_version else "",
        "dev_team": ss.get("rn_dev_team", ""),
        "release_owner": ss.get("rn_release_owner", ""),
        "senior_mgr": ss.get("rn_senior_mgr", ""),
        "director": ss.get("rn_director", ""),
        "svp": ss.get("rn_svp", ""),
        "environment": ss.get("rn_environment", ""),
        "extracted": ss.get("rn_extracted", []),
        "summary_p1": ss.get("rn_summary_p1", ""),
        "summary_p2": ss.get("rn_summary_p2", ""),
        "analyze_report_rows": ss.get("rn_analyze_report_rows", ""),
        "custom_report_tables": ss.get("rn_custom_report_tables", ""),
        "custom_clients": ss.get("rn_custom_clients", ""),
        "change_rows": ss.get("rn_change_rows", ""),
        "delivered_report_rows": ss.get("rn_delivered_report_rows", ""),
        "deployment_rows": ss.get("rn_deployment_rows", ""),
        "screenshot_names": ss.get("rn_testing_evidence_tickets", ss.get("rn_screenshot_names", "")),
        "testing_evidence_tickets": ss.get("rn_testing_evidence_tickets", ss.get("rn_screenshot_names", "")),
        "excluded_tickets": ss.get("rn_excluded_tickets", ""),
        "notes": ss.get("rn_notes", ""),
    }


def _build_script(ss: dict) -> str:
    """Build a self-contained generator script with user data + engine code (external mode)."""
    uses_fix_version = release_notes_uses_fix_version("rn_")
    version = ss.get("rn_version", "") if uses_fix_version else ""
    release_date = ss.get("rn_date", "") if uses_fix_version else ""
    dev_team = ss.get("rn_dev_team", "")
    release_owner = ss.get("rn_release_owner", "")
    senior_mgr = ss.get("rn_senior_mgr", "")
    director = ss.get("rn_director", "")
    svp = ss.get("rn_svp", "")
    environment = ss.get("rn_environment", "")

    summary_p1 = ss.get("rn_summary_p1", "")
    summary_p2 = ss.get("rn_summary_p2", "")
    custom_desc = ss.get("rn_custom_clients_desc", "")
    custom_clients = [c.strip() for c in ss.get("rn_custom_clients", "").split(",") if c.strip()]
    std_summary = ss.get("rn_std_summary", "")

    dashboard_items = _parse_dashboard_items(ss.get("rn_dashboard_items", ""))
    change_rows = _parse_change_rows(ss.get("rn_change_rows", ""))

    output_name = f"Release Notes {version.lstrip('v')}.docx" if version else "Release Notes.docx"
    output_dir = os.environ.get("RELEASE_NOTES_OUTPUT_DIR", tempfile.gettempdir())
    output_path = os.path.join(output_dir, output_name)

    gen_path = config.RELEASE_NOTES_GENERATOR
    if not os.path.exists(gen_path):
        return ""

    with open(gen_path, "r", encoding="utf-8") as f:
        full_script = f.read()

    engine_marker = _LEGACY_ENGINE_MARKER
    idx = full_script.find(engine_marker)
    if idx == -1:
        return ""

    box_end = full_script.rfind("\n", 0, idx)
    engine_code = full_script[box_end + 1:]

    header = full_script[: full_script.find("# " + "\u2554")]

    ref_doc = repr(os.environ.get("RELEASE_NOTES_REFERENCE_DOC", ""))
    out_doc = repr(output_path)

    lines = [
        "",
        "REFERENCE_DOC = " + ref_doc,
        "OUTPUT_DOC    = " + out_doc,
        "",
        "VERSION       = " + repr(version),
        "RELEASE_DATE  = " + repr(release_date),
        "DEV_TEAM      = " + repr(dev_team),
        "RELEASE_OWNER = " + repr(release_owner),
        "SENIOR_MGR    = " + repr(senior_mgr),
        "DIRECTOR      = " + repr(director),
        "GM            = " + repr(svp),
        "ENVIRONMENT   = " + repr(environment),
        "",
        "RELEASE_SUMMARY_PARA1 = [(" + repr(summary_p1) + ", False)]",
        "RELEASE_SUMMARY_PARA2 = [(" + repr(summary_p2) + ", False)]",
        "",
        "CUSTOM_CLIENTS_DESCRIPTION = " + repr(custom_desc),
        "",
        "CUSTOM_CLIENTS = " + repr(custom_clients),
        "",
        "STANDARD_CUSTOM_SUMMARY = [(" + repr(std_summary) + ", False)]",
        "",
        "DASHBOARD_ITEMS = " + repr(dashboard_items),
        "",
        "CHANGE_ROWS = " + repr(change_rows),
        "",
    ]
    data_section = "\n".join(lines)

    return header + data_section + "\n" + engine_code


def _render_preview(ss: dict) -> None:
    """Show a structured preview that closely mirrors the DOCX layout."""
    version = ss.get("rn_version", "")
    if version and not str(version).lower().startswith("v"):
        version = f"v{version}"
    release_date = ss.get("rn_date", "")
    dev_team = ss.get("rn_dev_team", "")
    release_owner = ss.get("rn_release_owner", "")
    senior_mgr = ss.get("rn_senior_mgr", "")
    director = ss.get("rn_director", "")
    svp = ss.get("rn_svp", "")
    environment = ss.get("rn_environment", "")
    summary_p1 = ss.get("rn_summary_p1", "")
    summary_p2 = ss.get("rn_summary_p2", "")
    analyze_rows = parse_analyze_report_rows(ss.get("rn_analyze_report_rows", ""))
    custom_tables = parse_custom_client_report_tables(ss.get("rn_custom_report_tables", ""))
    custom_clients_str = ss.get("rn_custom_clients", "")
    change_raw = ss.get("rn_change_rows", "")

    change_rows = _parse_change_rows(change_raw)
    highlight_blocks = build_highlight_summary_tables(ss.get("rn_extracted", []))
    highlight_lines = [ln.strip() for ln in summary_p2.splitlines() if ln.strip()]

    st.markdown("### Release Notes")
    if version:
        st.markdown(f"**Version:** {esc(version)}")
    meta_lines = [
        ("Development Team", dev_team),
        ("Release Owner", release_owner),
        ("Senior Manager", senior_mgr),
        ("Director", director),
        ("GM", svp),
        ("Environment", environment),
    ]
    if release_date:
        meta_lines.insert(0, ("Release Date", release_date))
    for label, value in meta_lines:
        st.markdown(f"**{esc(label)}:** {esc(value)}")

    st.markdown("#### Release Summary")
    if summary_p1:
        st.markdown(summary_p1)

    if highlight_blocks:
        st.markdown("**Key Highlights**")
        for block in highlight_blocks:
            st.markdown(f"##### {esc(block.title)}")
            st.dataframe(
                pd.DataFrame(block.rows, columns=list(block.headers)),
                use_container_width=True,
                hide_index=True,
            )
    elif highlight_lines:
        st.markdown("**Key Highlights**")
        for line in highlight_lines:
            st.markdown(f"- {esc(line)}")

    custom_clients = [c.strip() for c in custom_clients_str.split(",") if c.strip()]
    delivered_raw = ss.get("rn_delivered_report_rows", "")
    delivered_rows = [
        [c.strip() for c in ln.split("|", 2)]
        for ln in delivered_raw.splitlines()
        if ln.strip()
    ]
    if not delivered_rows and ss.get("rn_extracted"):
        from generators.release_notes_report_tables import build_delivered_reports_rows

        delivered_rows = build_delivered_reports_rows(ss.get("rn_extracted", []))
    if delivered_rows:
        st.markdown("**Reports / Dashboards Delivered**")
        st.dataframe(
            pd.DataFrame(delivered_rows, columns=list(DELIVERED_REPORTS_HEADERS)),
            use_container_width=True,
            hide_index=True,
        )

    deploy_raw = ss.get("rn_deployment_rows", "")
    deploy_rows = [
        [c.strip() for c in ln.split("|", 3)]
        for ln in deploy_raw.splitlines()
        if ln.strip()
    ]
    st.markdown("#### Deployment Tracking")
    st.dataframe(
        pd.DataFrame(deploy_rows, columns=DEPLOYMENT_HEADERS),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Ticket Details")
    if change_rows:
        st.dataframe(
            pd.DataFrame(change_rows, columns=CHANGE_HEADERS),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No ticket detail rows yet — generated DOCX will include the 4-column header table.")

    evidence_tickets = [
        ln.strip()
        for ln in (
            ss.get("rn_testing_evidence_tickets", "") or ss.get("rn_screenshot_names", "")
        ).splitlines()
        if ln.strip()
    ]
    st.markdown(f"#### {TESTING_EVIDENCE_HEADING.rstrip(':')}")
    st.markdown(f"**{TESTING_EVIDENCE_SUBHEADING}**")
    if evidence_tickets:
        for ticket in evidence_tickets:
            st.markdown(f"- {esc(ticket)}")
    else:
        st.caption(
            "Included ticket keys appear here and in the generated DOCX; "
            "edit the list in Step 3 if needed."
        )

    excluded = ss.get("rn_excluded_tickets", "").strip()
    st.markdown("#### Tickets Excluded from Deployment")
    if excluded:
        for line in excluded.splitlines():
            if line.strip():
                st.markdown(f"- {esc(line.strip())}")
    else:
        st.caption(
            f"Generated DOCX includes an 8-column excluded-tickets table "
            f"({', '.join(EXCLUDED_HEADERS[:3])}, …) with a gray placeholder row when empty."
        )

    notes = ss.get("rn_notes", "").strip()
    st.markdown("#### Notes")
    if notes:
        st.markdown(notes)
    else:
        st.caption("Heading included in generated DOCX; add notes in Step 3 if needed.")


def _prepare_data_dict(ss: dict) -> dict:
    """Build generator payload and fill deployment gaps from deployer/history."""
    from generators.release_notes_deployment import (
        build_deployment_rows,
        enrich_deployment_rows,
        format_deployment_rows,
        parse_deployment_rows,
    )
    from generators.release_notes_quality import canonical_client_name, improve_extracted
    from release_platform.ui.helpers import collect_release_notes_deploy_info

    data = _build_data_dict(ss)
    version_label = str(data.get("version", "")).lstrip("vV")
    deploy_info = collect_release_notes_deploy_info(version_label or None)
    rows = parse_deployment_rows(data.get("deployment_rows", ""))
    if not rows:
        extracted = data.get("extracted") or []
        owners: dict[str, str] = {}
        for entry in improve_extracted(extracted):
            if entry.get("type") == "Analyze":
                label = "Analyze"
            else:
                label = canonical_client_name(entry.get("client") or "") or entry.get("client") or "Custom"
            if label not in owners:
                owners[label] = entry.get("assignee", "")
        if owners:
            data["deployment_rows"] = build_deployment_rows(owners, deploy_info or {})
    elif deploy_info:
        data["deployment_rows"] = format_deployment_rows(
            enrich_deployment_rows(rows, deploy_info)
        )
    return data


def _reload_generator_module():
    """Reload generator modules only when GENERATOR_BUILD_ID changes."""
    from generators.release_notes_generator import GENERATOR_BUILD_ID

    cached = st.session_state.get("_rn_generator_reload_cache")
    if isinstance(cached, dict) and cached.get("build_id") == GENERATOR_BUILD_ID:
        import generators.release_notes_generator as gen_mod

        return gen_mod

    import importlib

    import generators.release_notes_docx_styles as styles_mod
    import generators.release_notes_generator as gen_mod
    import generators.release_notes_template_defaults as defaults_mod

    importlib.reload(defaults_mod)
    importlib.reload(styles_mod)
    gen_mod = importlib.reload(gen_mod)
    st.session_state["_rn_generator_reload_cache"] = {
        "build_id": GENERATOR_BUILD_ID,
    }
    return gen_mod


def _generate_builtin(ss: dict) -> None:
    """Generate the DOCX using the built-in generator and offer download."""
    from generators.release_notes_publish import publish_release_notes_docx

    gen_mod = _reload_generator_module()
    build_id = gen_mod.GENERATOR_BUILD_ID
    st.session_state["_generator_build_id"] = build_id

    data = _prepare_data_dict(ss)

    with st.spinner("Generating release notes\u2026"):
        publish = publish_release_notes_docx(data, enforce_readiness=True)
        if publish.status == "blocked":
            st.error("Release Notes blocked by readiness checks. Resolve blockers on Step 3/4 first.")
            if publish.readiness:
                for item in publish.readiness.blockers:
                    st.markdown(f"- {esc(item.message)}")
            return
        if publish.status != "ok" or not publish.docx_bytes:
            st.error(f"Generation failed: {publish.error or 'Unknown error'}")
            return
        docx_bytes = publish.docx_bytes

    hyperlink_check = publish.hyperlink_check or {}
    rows_with_links = hyperlink_check.get("rows_with_links", 0)
    hyperlink_count = hyperlink_check.get("hyperlink_count", 0)

    version = ss.get("rn_version", "")
    output_name = f"Release Notes {version.lstrip('v')}.docx" if version else "Release Notes.docx"
    st.session_state["rn_docx_bytes"] = docx_bytes
    st.session_state["rn_docx_filename"] = output_name
    mark_release_doc_generated(output_name)

    st.markdown(
        f'<div class="success-banner">'
        f"<h3>Document Generated</h3>"
        f"<p>Ready for download: {esc(output_name)}</p>"
        f"<p style='opacity:.75;font-size:.85rem'>Generator build: {esc(build_id)}</p>"
        f"<p style='opacity:.75;font-size:.75rem'>Verify in Word: File → Info → Keywords = {esc(build_id)}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if rows_with_links:
        min_expected = rows_with_links  # at least one hyperlink per linked row (Ticket#)
        if hyperlink_count < min_expected:
            st.error(
                f"**Hyperlink check failed** — expected clickable links for {rows_with_links} "
                f"change row(s), but found {hyperlink_count} in the DOCX. "
                "Do not use this file; restart the app and generate again."
            )
        else:
            st.success(
                f"Ticket Details hyperlinks verified: **{hyperlink_count}** clickable link(s) "
                f"across Ticket#, Parent, and Link columns."
            )
    else:
        st.caption("No Jira links in change rows — hyperlink columns were skipped.")

    st.download_button(
        "\u2b07\ufe0f Download Release Notes",
        data=docx_bytes,
        file_name=output_name,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key="rn_download_docx",
    )


def _generate_external(ss: dict) -> None:
    """Generate the DOCX using the external generator script."""
    version = ss.get("rn_version", "")
    script_content = _build_script(dict(ss))
    if not script_content:
        st.error("Failed to build generator script. Check the engine marker in the source file.")
        return

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(script_content)
        tmp_path = tmp.name

    with st.spinner("Generating release notes\u2026"):
        try:
            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                output_name = (
                    f"Release Notes {version.lstrip('v')}.docx"
                    if version
                    else "Release Notes.docx"
                )
                ext_output_dir = os.environ.get("RELEASE_NOTES_OUTPUT_DIR", tempfile.gettempdir())
                output_path = os.path.join(ext_output_dir, output_name)
                mark_release_doc_generated(output_name)
                st.markdown(
                    f'<div class="success-banner">'
                    f"<h3>Document Generated</h3>"
                    f"<p>{esc(output_path)}</p>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if os.path.isfile(output_path):
                    with open(output_path, "rb") as docx_file:
                        docx_bytes = docx_file.read()
                        st.session_state["rn_docx_bytes"] = docx_bytes
                        st.session_state["rn_docx_filename"] = output_name
                        st.download_button(
                            "\u2b07\ufe0f Download Release Notes",
                            data=docx_bytes,
                            file_name=output_name,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key="rn_download_docx_external",
                        )
                if result.stdout.strip():
                    st.code(result.stdout.strip())
            else:
                st.error("Generation failed:")
                st.code(result.stderr or result.stdout)
        except subprocess.TimeoutExpired:
            st.error("Generation timed out after 120 seconds.")
        except Exception as exc:
            st.error(f"Error: {exc}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _render_edit_regenerate_tab(ss: dict) -> None:
    """Quick edits on Step 4 — changes persist; regenerate from Download tab."""
    st.markdown(
        '<div class="jt-banner jt-banner--info" style="margin-bottom:12px">'
        "<strong>Edits are saved in your session.</strong> After changing anything here, "
        "open the <strong>Download DOCX</strong> tab and click <strong>Generate .docx</strong> "
        "again. Your previous download is not updated automatically."
        "</div>",
        unsafe_allow_html=True,
    )
    doc_name = ss.get("shared_docx_filename") or st.session_state.get("shared_docx_filename", "")
    if st.session_state.get("shared_docx_generated") and doc_name:
        st.success(f"Last generated: **{esc(doc_name)}** — regenerate after edits below.")

    st.markdown("### Metadata")
    c1, c2 = st.columns(2)
    with c1:
        ss["rn_release_owner"] = st.text_input(
            "Release Owner",
            value=ss.get("rn_release_owner", ""),
            key="_rn_s4_owner",
        )
        ss["rn_dev_team"] = st.text_input(
            "Dev Team",
            value=ss.get("rn_dev_team", ""),
            key="_rn_s4_team",
        )
    with c2:
        ss["rn_environment"] = st.text_input(
            "Environment",
            value=ss.get("rn_environment", "Production"),
            key="_rn_s4_env",
        )
        ss["rn_date"] = st.text_input(
            "Release Date",
            value=ss.get("rn_date", ""),
            key="_rn_s4_date",
        )

    st.markdown("### Release Summary")
    ss["rn_summary_p1"] = st.text_area(
        "Summary paragraph",
        value=ss.get("rn_summary_p1", ""),
        height=80,
        key="_rn_s4_sp1",
    )

    st.markdown("### Tables")
    ss["rn_deployment_rows"] = st.text_area(
        "Deployment rows",
        value=ss.get("rn_deployment_rows", ""),
        height=80,
        key="_rn_s4_deploy",
    )
    ss["rn_change_rows"] = st.text_area(
        "Ticket detail rows",
        value=ss.get("rn_change_rows", ""),
        height=160,
        key="_rn_s4_change",
    )

    st.markdown("### Post-deploy sections")
    ss["rn_excluded_tickets"] = st.text_area(
        "Excluded tickets",
        value=ss.get("rn_excluded_tickets", ""),
        height=60,
        key="_rn_s4_excl",
    )
    ss["rn_notes"] = st.text_area(
        "Notes",
        value=ss.get("rn_notes", ""),
        height=60,
        key="_rn_s4_notes",
    )

    if st.button("Open full editor (Step 3) →", key="rn_s4_full_edit"):
        _go(3)


def render() -> None:
    st.markdown("## Preview & Generate")

    ensure_release_notes_draft()
    sync_release_doc_metadata("rn_")
    persist_rn_readiness_payload(dict(st.session_state))
    ss = st.session_state

    st.markdown("### Release Notes Readiness")
    readiness_report = render_release_notes_readiness(dict(ss), show_apply_summary=False)
    render_release_notes_e2e_checklist(dict(ss))

    if release_notes_uses_fix_version("rn_"):
        derived_version, derived_date = derive_release_doc_metadata("rn_")
        if derived_version and ss.get("rn_metadata_customized"):
            st.caption(
                f"Preview uses your edited values. Fix version is "
                f"`{derived_version}`, `{derived_date}`."
            )
    else:
        st.caption(
            "Status-only release — generated document omits version and release date."
        )

    st.markdown(
        '<div class="jt-banner jt-banner--info" style="margin-bottom:8px">'
        "<strong>Generate your file here</strong> — the "
        "<strong>Download DOCX</strong> tab is selected by default. "
        "Click <strong>Generate .docx</strong>, then paste your SharePoint link below."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<style>
section.main div[data-testid="stTabs"] [data-baseweb="tab-list"] button:first-child {
  font-weight: 800 !important;
  color: var(--jt-accent) !important;
  background: var(--jt-accent-soft) !important;
  border-radius: 10px 10px 0 0 !important;
  border-bottom: 3px solid var(--jt-accent) !important;
}
section.main div[data-testid="stTabs"] [data-baseweb="tab-list"] button:first-child[aria-selected="true"] {
  box-shadow: 0 -2px 12px rgba(99, 102, 241, 0.2);
}
</style>
        """,
        unsafe_allow_html=True,
    )
    tab_download, tab_preview, tab_edit = st.tabs(
        ["📥 Download DOCX", "Preview in Browser", "Edit & Regenerate"]
    )

    with tab_download:
        from generators.release_notes_generator import GENERATOR_BUILD_ID

        live_build = st.session_state.get("_generator_build_id") or GENERATOR_BUILD_ID
        st.info(
            f"**Built-in generator** — live build **`{live_build}`**. "
            "Click Generate below (do not reuse an old file from Downloads)."
        )
        use_external = _has_external_generator_cached() and os.environ.get("RELEASE_NOTES_ALLOW_LEGACY_EXTERNAL") == "1"
        ensure_release_notes_draft()
        persist_rn_readiness_payload(dict(st.session_state))
        live_readiness = assess_readiness_cached(dict(st.session_state))
        generate_blocked = not live_readiness.ready
        if generate_blocked:
            st.error("Resolve readiness blockers before generating the final DOCX.")
            for item in live_readiness.blockers:
                st.markdown(f"- **{esc(item.message)}** — _{esc(item.action)}_")
            fix_cols = st.columns([1, 2])
            with fix_cols[0]:
                if st.button(
                    "Auto-fill missing fields from tickets",
                    key="rn_s4_autofix_draft",
                    type="primary",
                ):
                    ensure_release_notes_draft()
                    persist_rn_readiness_payload(dict(st.session_state))
                    st.rerun()
            with fix_cols[1]:
                st.caption(
                    "Restores tickets from saved Step 2 data when needed and rebuilds Ticket Details "
                    "and summary tables. Version and release date are filled only when tickets were "
                    "loaded **by fix version**."
                )

        if _has_external_generator_cached() and not use_external:
            st.warning(
                "A legacy external generator script is configured but disabled. "
                "The built-in generator is used for full layout parity. "
                "Set RELEASE_NOTES_ALLOW_LEGACY_EXTERNAL=1 only if you must use the old script."
            )

        if use_external:
            st.caption(
                "Using **external generator** configured in workspace settings. "
                "Remove `generator_script` from release notes config to use the built-in generator."
            )
            if st.button(
                "\U0001f4c4 Generate .docx (external)",
                type="primary",
                key="rn_generate",
                disabled=generate_blocked,
            ):
                _generate_external(dict(ss))
        else:
            if st.button(
                "\U0001f4c4 Generate .docx",
                type="primary",
                key="rn_generate",
                disabled=generate_blocked,
            ):
                _generate_builtin(dict(ss))

    with tab_preview:
        _render_preview(ss)

    with tab_edit:
        _render_edit_regenerate_tab(dict(ss))

    _render_sharepoint_section(dict(ss))

    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("\u2190 Back to Edit", key="rn_s4_back"):
            _go(3)
    with c2:
        if st.button("\U0001f3e0 Home", key="rn_s4_home"):
            st.session_state.pop("active_app", None)
            for k in list(st.session_state.keys()):
                if k.startswith(("rn_", "_rn_")):
                    del st.session_state[k]
            for key in (
                "shared_docx_generated",
                "shared_docx_filename",
                "rn_docx_bytes",
            ):
                st.session_state.pop(key, None)
            st.rerun()
    with c3:
        stk_ready = check_app_prerequisites("service_ticket").ok
        if st.button(
            "Service Ticket \u2192",
            type="primary",
            key="rn_s4_next_app",
            disabled=not stk_ready,
        ):
            navigate_to_app("service_ticket")
        if not stk_ready:
            render_action_hint(
                "Generate the .docx, upload it to SharePoint, paste the link above, "
                "then continue to Service Ticket."
            )
        else:
            render_action_hint(
                "Opens Service Ticket with your locked ticket list and SharePoint link pre-filled."
            )

    st.caption(
        "E2E CLI: `python scripts/test_release_notes_e2e.py` · "
        "`python scripts/test_release_notes_e2e.py --live --version YOUR.FIX.VERSION`"
    )


def _render_sharepoint_section(ss: dict) -> None:
    """Manual SharePoint link (Graph auto-upload archived when flagged)."""
    doc_name = ss.get("shared_docx_filename") or st.session_state.get("shared_docx_filename", "")
    expected_name = release_notes_doc_filename("rn_")
    doc_ok = bool(st.session_state.get("shared_docx_generated"))

    st.markdown("### SharePoint link")
    if doc_ok and doc_name:
        st.success(f"Release Notes document generated: **{esc(doc_name)}**")
    else:
        st.warning("Generate the Release Notes `.docx` first in the Download DOCX tab.")

    if config.sharepoint_upload_archived():
        st.info(
            "Automatic SharePoint upload is archived. Upload the `.docx` manually, "
            "then paste the sharing link below for the SHIPIT description."
        )
    else:
        upload_cfg = sharepoint_upload.load_upload_config(config.SHAREPOINT_UPLOAD)
        upload_status = sharepoint_upload.status(upload_cfg)
        docx_bytes = st.session_state.get("rn_docx_bytes")
        can_attempt = bool(doc_ok and docx_bytes)

        if upload_status["can_upload"]:
            st.caption(
                f"Graph upload is ready. Destination: `{upload_status['folder_path']}`."
            )
        else:
            missing = upload_status["graph"].get("missing") or []
            detail = ", ".join(missing) if missing else "SharePoint target / enable flag"
            st.info(
                "Automatic upload is wired but not active yet. "
                f"Pending setup: **{detail}**. Preview the upload plan now "
                "or paste a SharePoint link below."
            )

        upload_col, plan_col, _ = st.columns([1, 1, 2])
        with upload_col:
            if st.button(
                "Upload to SharePoint",
                key="rn_upload_sharepoint",
                type="primary",
                use_container_width=True,
                disabled=not can_attempt,
            ):
                _run_sharepoint_upload(
                    upload_cfg,
                    bytes(docx_bytes),
                    st.session_state.get("rn_docx_filename") or doc_name,
                    dry_run=False,
                )
        with plan_col:
            if st.button(
                "Preview upload plan",
                key="rn_preview_sharepoint_upload",
                use_container_width=True,
                disabled=not can_attempt,
            ):
                _run_sharepoint_upload(
                    upload_cfg,
                    bytes(docx_bytes),
                    st.session_state.get("rn_docx_filename") or doc_name,
                    dry_run=True,
                )

        preview = st.session_state.get("_rn_sharepoint_upload_preview")
        if isinstance(preview, dict):
            if preview.get("ok") and preview.get("dry_run"):
                plan = preview.get("plan") or {}
                st.success(
                    "Upload plan ready: "
                    f"`{plan.get('folder_path', '')}/{plan.get('remote_name', '')}` "
                    f"({plan.get('bytes_size', 0):,} bytes)."
                )
            elif not preview.get("ok"):
                st.error(preview.get("error") or "SharePoint upload failed.")

    st.caption(
        f"Service Ticket will embed this link as **{esc(expected_name)}** "
        f"in the SHIPIT description (same as production format)."
    )

    current = st.session_state.get("shared_sharepoint_url", "")
    url = st.text_input(
        "SharePoint link to Release Notes .docx",
        value=current,
        placeholder="https://yourorg.sharepoint.com/sites/.../Release%20Notes.docx",
        key="_rn_sharepoint_url",
        help="Required before creating a Service Ticket. Included in the SHIPIT description.",
    )
    if url != current:
        save_sharepoint_url(url)

    if url.strip() and not validate_sharepoint_url(url):
        from sharepoint_url import sharepoint_validation_message

        st.error(
            sharepoint_validation_message(url)
            or "Enter a valid URL starting with http:// or https://"
        )
    elif validate_sharepoint_url(url):
        st.caption("SharePoint link saved — Service Ticket can use this in the description.")


def _run_sharepoint_upload(
    cfg: sharepoint_upload.SharePointUploadConfig,
    docx_bytes: bytes,
    filename: str,
    *,
    dry_run: bool,
) -> None:
    """Bridge in-memory generated bytes to the path-based Graph backend."""
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(docx_bytes)
            tmp_path = tmp.name
        result = sharepoint_upload.upload_release_notes(
            cfg,
            tmp_path,
            remote_name=filename if filename else None,
            version=str(st.session_state.get("rn_version") or ""),
            reference_date=st.session_state.get("rn_date"),
            dry_run=dry_run or not cfg.can_upload(),
        )
        payload = result.to_dict()
        st.session_state["_rn_sharepoint_upload_preview"] = payload
        if result.ok and not result.dry_run and result.web_url:
            save_sharepoint_url(result.web_url)
            st.session_state.pop("_rn_sharepoint_upload_preview", None)
            st.success("Release Notes uploaded to SharePoint and linked to Service Ticket.")
            st.rerun()
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
