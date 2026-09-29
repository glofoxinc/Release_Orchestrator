"""Shared session-state helpers, history I/O, and environment management."""

from __future__ import annotations

import html as _html
import importlib
import json
import logging
import os
import re
from datetime import date, datetime
from typing import Any

import streamlit as st

import config
import deployment_history
import jira_client
import team_scope
from generators.release_notes_deployment import (
    parse_deployment_id_time,
)

logger = logging.getLogger(__name__)

# Bump when UI behavior changes — shown in sidebar so users can confirm reload.
UI_BUILD_ID = "2026.09.09-rn-format-v6-layout"

# Bump when Release Deployer step count/order changes (invalidates stale wiz_step).
DEPLOYER_WIZARD_VERSION = 3


def esc(text: str) -> str:
    """Escape text for safe insertion into HTML."""
    return _html.escape(text, quote=True)


APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(APP_DIR, ".env")


def _history_path() -> str:
    """Return workspace-aware history file path."""
    return deployment_history.history_path()
INITIAL_RELEASE_NAMES = {"initial release", "initial version"}

_FIX_VERSION_RE = re.compile(r"(\d{4})\.(\d)\.(\d{2})\.(\d{2})")
_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

RN_DRAFT_RESET_KEYS = (
    "rn_extracted",
    "rn_all_extracted",
    "rn_selected_keys",
    "rn_source_fp",
    "rn_version",
    "rn_date",
    "rn_release_fp",
    "rn_metadata_customized",
    "rn_dev_team",
    "rn_release_owner",
    "rn_senior_mgr",
    "rn_director",
    "rn_svp",
    "rn_environment",
    "rn_ticket_fp",
    "rn_summary_p1",
    "rn_summary_p2",
    "rn_analyze_report_rows",
    "rn_custom_report_tables",
    "rn_custom_clients",
    "rn_change_rows",
    "rn_deployment_rows",
    "rn_delivered_report_rows",
    "rn_sanity_checklist",
    "rn_screenshot_names",
    "rn_testing_evidence_tickets",
    "rn_excluded_tickets",
    "rn_notes",
)

RN_TICKET_DRAFT_KEYS = (
    "rn_summary_p1",
    "rn_summary_p2",
    "rn_analyze_report_rows",
    "rn_custom_report_tables",
    "rn_custom_clients",
    "rn_change_rows",
    "rn_deployment_rows",
    "rn_delivered_report_rows",
    "rn_sanity_checklist",
    "rn_screenshot_names",
    "rn_testing_evidence_tickets",
    "rn_excluded_tickets",
    "rn_notes",
)

STK_PLAN_KEYS = (
    "stk_impl_plan",
    "stk_test_plan",
    "stk_backout_plan",
    "stk_business_impact",
)


def parse_fix_version_name(name: str) -> tuple[str, str] | None:
    """Parse fix version names like ``2026.3.07.06`` into doc version + date labels."""
    match = _FIX_VERSION_RE.search((name or "").strip())
    if not match:
        return None
    year, quarter, month_str, day_str = match.groups()
    month = int(month_str)
    day = int(day_str)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    version_label = f"v{year}.{quarter}.{month_str}.{day_str}"
    date_label = f"{day:02d}-{_MONTH_NAMES[month]}-{year}"
    return version_label, date_label


def parse_fix_version_date(name: str) -> date | None:
    """Return a calendar date parsed from a fix version name."""
    match = _FIX_VERSION_RE.search((name or "").strip())
    if not match:
        return None
    year, _, month_str, day_str = match.groups()
    try:
        return date(int(year), int(month_str), int(day_str))
    except ValueError:
        return None


def release_selection_fingerprint(prefix: str) -> str:
    """Stable id for the currently selected releases in one app."""
    parts: list[str] = []
    for proj in config.PROJECTS:
        rel = st.session_state.get(f"{prefix}release_{proj['key']}", {})
        parts.append(f"{proj['key']}:{rel.get('id', '')}")
    return "|".join(parts)


def service_ticket_uses_fix_version(
    prefix: str = "stk_",
    ss: dict[str, Any] | None = None,
) -> bool:
    """True when SHIPIT should show fix-version metadata (summary version, schedule)."""
    return release_notes_uses_fix_version(prefix, ss)


def release_notes_uses_fix_version(
    prefix: str = "rn_",
    ss: dict[str, Any] | None = None,
) -> bool:
    """True when Release Notes should show fix-version metadata (version + release date)."""
    from release_platform.ui import ticket_source as ts

    if ss is None:
        return ts.get_effective_selection_mode(prefix) == ts.MODE_FIX_VERSION

    locked = ss.get(ts.locked_source_key(prefix))
    if isinstance(locked, dict) and locked.get("mode") in {ts.MODE_FIX_VERSION, ts.MODE_STATUS}:
        return locked["mode"] == ts.MODE_FIX_VERSION
    mode = ss.get(ts.mode_session_key(prefix), ts.MODE_FIX_VERSION)
    return mode == ts.MODE_FIX_VERSION


def clear_release_doc_version_metadata(prefix: str = "rn_", *, meta_prefix: str = "") -> None:
    """Remove version/date fields for status-only Release Notes drafts."""
    key_ver = f"{meta_prefix}version" if meta_prefix else "rn_version"
    key_date = f"{meta_prefix}date" if meta_prefix else "rn_date"
    key_custom = f"{meta_prefix}metadata_customized" if meta_prefix else "rn_metadata_customized"
    key_fp = f"{meta_prefix}release_fp" if meta_prefix else "rn_release_fp"
    for key in (key_ver, key_date, key_custom, key_fp, "_rn_ver", "_rn_dt"):
        st.session_state.pop(key, None)


def release_doc_metadata_fallback_today(*, on: date | None = None) -> tuple[str, str]:
    """Build vYYYY.Q.MM.DD + date label when a fix-version label is needed but unparsed."""
    d = on or date.today()
    quarter = (d.month - 1) // 3 + 1
    version = f"v{d.year}.{quarter}.{d.month:02d}.{d.day:02d}"
    date_label = f"{d.day:02d}-{_MONTH_NAMES[d.month]}-{d.year}"
    return version, date_label


def release_doc_metadata_fallback_status_mode(*, on: date | None = None) -> tuple[str, str]:
    """Status-mode default deploy date: tomorrow (T+1), matching MCP wizard."""
    if on is not None:
        return release_doc_metadata_fallback_today(on=on)
    tomorrow = date.fromordinal(date.today().toordinal() + 1)
    return release_doc_metadata_fallback_today(on=tomorrow)


def derive_release_doc_metadata(prefix: str) -> tuple[str, str]:
    """Build version/date labels from selected Jira fix versions."""
    return derive_release_doc_metadata_from_state(st.session_state, prefix)


def derive_release_doc_metadata_from_state(
    ss: dict[str, Any],
    prefix: str,
) -> tuple[str, str]:
    """Build version/date labels from release selections in a state dict."""
    version_labels: list[str] = []
    date_labels: list[str] = []

    for proj in config.PROJECTS:
        rel = ss.get(f"{prefix}release_{proj['key']}", {}) or {}
        if not rel:
            continue
        name = rel.get("name", "")
        parsed = parse_fix_version_name(name)
        if parsed:
            version_labels.append(parsed[0])
            date_labels.append(parsed[1])
        elif name:
            version_labels.append(name if name.lower().startswith("v") else f"v{name}")

    if not version_labels:
        return "", ""

    unique_versions = list(dict.fromkeys(version_labels))
    version = unique_versions[0] if len(unique_versions) == 1 else " + ".join(unique_versions)
    unique_dates = list(dict.fromkeys(date_labels))
    doc_date = unique_dates[0] if len(unique_dates) == 1 else " + ".join(unique_dates)
    return version, doc_date


def resolve_rn_extracted_from_state(ss: dict[str, Any]) -> list[dict[str, Any]]:
    """Rebuild rn_extracted from persisted fallbacks (restore / Step 4 heal)."""
    extracted = list(ss.get("rn_extracted") or [])
    if extracted:
        return extracted

    all_extracted = list(ss.get("rn_all_extracted") or [])
    if not all_extracted:
        return []

    selected = ss.get("rn_selected_keys")
    if selected:
        selected_set = {str(key).strip() for key in selected if str(key).strip()}
        if selected_set:
            return [entry for entry in all_extracted if entry.get("ticket") in selected_set]

    from generators.parsing import parse_change_rows as _parse_change_rows

    row_keys = {
        (row[0] or "").strip().upper()
        for row in _parse_change_rows(ss.get("rn_change_rows") or "")
        if row and (row[0] or "").strip() and "-" in row[0]
    }
    if row_keys:
        return [
            entry
            for entry in all_extracted
            if str(entry.get("ticket") or "").strip().upper() in row_keys
        ]

    if ss.get("rn_change_rows") or ss.get("rn_summary_p1") or ss.get("rn_analyze_report_rows"):
        return all_extracted
    return []


def build_rn_readiness_payload(ss: dict[str, Any]) -> dict[str, Any]:
    """Map session state to readiness input, resolving version/date when tickets exist."""
    from generators.release_notes_insights import readiness_data_from_session

    data = readiness_data_from_session(ss)
    uses_fix_version = release_notes_uses_fix_version("rn_", ss)
    data["include_fix_version_metadata"] = uses_fix_version
    resolved = resolve_rn_extracted_from_state(ss)
    if resolved and not data.get("extracted"):
        data["extracted"] = resolved
    has_draft = bool(data.get("extracted") or data.get("change_rows"))
    if not uses_fix_version:
        data["include_fix_version_metadata"] = True
        if not str(data.get("version") or "").strip() and has_draft:
            deploy_on = ss.get("stk_planned_start_date")
            version, doc_date = release_doc_metadata_fallback_today(
                on=deploy_on if isinstance(deploy_on, date) else None,
            )
            data["version"] = version
            data["release_date"] = doc_date
    elif not str(data.get("version") or "").strip() and has_draft:
        version, doc_date = derive_release_doc_metadata_from_state(ss, "rn_")
        if not version:
            version, doc_date = release_doc_metadata_fallback_today()
        data["version"] = version
        if not str(data.get("release_date") or "").strip():
            data["release_date"] = doc_date
    meta = config.RELEASE_META
    if not str(data.get("dev_team") or "").strip():
        data["dev_team"] = meta.get("dev_team", "")
    if not str(data.get("release_owner") or "").strip():
        data["release_owner"] = meta.get("release_owner", "")
    return data


def heal_session_after_restore() -> None:
    """Fill Release Notes draft gaps after session restore (version, tickets, tables)."""
    try:
        from release_platform.ui.release_notes.step3_edit import ensure_release_notes_draft

        ensure_release_notes_draft()
        persist_rn_readiness_payload(dict(st.session_state))
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).debug(
            "heal_session_after_restore failed",
            exc_info=True,
        )


def persist_rn_readiness_payload(ss: dict[str, Any]) -> None:
    """Write resolved readiness fields back into Streamlit session state."""
    resolved = resolve_rn_extracted_from_state(ss)
    if resolved and not (ss.get("rn_extracted") or st.session_state.get("rn_extracted")):
        st.session_state["rn_extracted"] = resolved
    payload = build_rn_readiness_payload(ss)
    if payload.get("extracted") and not (st.session_state.get("rn_extracted") or []):
        st.session_state["rn_extracted"] = payload["extracted"]
    if payload.get("include_fix_version_metadata"):
        if str(payload.get("version") or "").strip():
            st.session_state["rn_version"] = payload["version"]
        if str(payload.get("release_date") or "").strip():
            st.session_state["rn_date"] = payload["release_date"]
    else:
        clear_release_doc_version_metadata("rn_")
    st.session_state.pop("_rn_readiness_cache", None)
    if str(payload.get("dev_team") or "").strip():
        st.session_state["rn_dev_team"] = payload["dev_team"]
    if str(payload.get("release_owner") or "").strip():
        st.session_state["rn_release_owner"] = payload["release_owner"]


def release_notes_doc_filename(prefix: str = "rn_") -> str:
    """Canonical Release Notes .docx label for SharePoint links (no duplicate PIC+AN names)."""
    shared = st.session_state.get("shared_docx_filename", "")
    if shared:
        return os.path.basename(str(shared))
    if prefix.rstrip("_") == "rn" and not release_notes_uses_fix_version(prefix):
        generated = st.session_state.get("rn_docx_filename")
        if generated:
            return os.path.basename(str(generated))
        deploy_on = st.session_state.get("stk_planned_start_date")
        version, _ = release_doc_metadata_fallback_today(
            on=deploy_on if isinstance(deploy_on, date) else None,
        )
        if version:
            return f"Release Notes {version.lstrip('v')}.docx"
        return "Release Notes.docx"
    version, _ = derive_release_doc_metadata(prefix)
    if version:
        return f"Release Notes {version.lstrip('v')}.docx"
    return "Release Notes.docx"


def sync_sharepoint_from_shared(*, force: bool = False) -> None:
    """Copy Release Notes SharePoint URL into Service Ticket session when unset."""
    shared = (st.session_state.get("shared_sharepoint_url") or "").strip()
    if not shared:
        return
    current = (st.session_state.get("stk_sharepoint") or "").strip()
    if force or not current:
        st.session_state["stk_sharepoint"] = shared


def sync_release_doc_metadata(prefix: str, *, meta_prefix: str = "") -> None:
    """Refresh version/date from selected fix versions unless the user customized them."""
    if prefix.rstrip("_") == "rn" and not release_notes_uses_fix_version(prefix):
        key_ver = f"{meta_prefix}version" if meta_prefix else "rn_version"
        key_date = f"{meta_prefix}date" if meta_prefix else "rn_date"
        key_custom = f"{meta_prefix}metadata_customized" if meta_prefix else "rn_metadata_customized"
        if not bool(st.session_state.get(key_custom)):
            deploy_on = st.session_state.get("stk_planned_start_date")
            if isinstance(deploy_on, date):
                version, doc_date = release_doc_metadata_fallback_today(on=deploy_on)
            else:
                version, doc_date = release_doc_metadata_fallback_status_mode()
            st.session_state[key_ver] = version
            st.session_state[key_date] = doc_date
            st.session_state.pop("_rn_ver", None)
            st.session_state.pop("_rn_dt", None)
        return
    fp = release_selection_fingerprint(prefix)
    version, doc_date = derive_release_doc_metadata(prefix)
    key_fp = f"{meta_prefix}release_fp" if meta_prefix else "rn_release_fp"
    key_ver = f"{meta_prefix}version" if meta_prefix else "rn_version"
    key_date = f"{meta_prefix}date" if meta_prefix else "rn_date"
    key_custom = f"{meta_prefix}metadata_customized" if meta_prefix else "rn_metadata_customized"

    if not version:
        return

    fp_changed = st.session_state.get(key_fp) != fp
    customized = bool(st.session_state.get(key_custom))
    stored_ver = st.session_state.get(key_ver, "")
    stored_date = st.session_state.get(key_date, "")
    drifted = stored_ver != version or stored_date != doc_date

    if fp_changed:
        st.session_state[key_fp] = fp
        st.session_state[key_custom] = False
        customized = False

    if not customized and (fp_changed or drifted or key_ver not in st.session_state):
        st.session_state[key_ver] = version
        st.session_state[key_date] = doc_date
        # Drop legacy widget keys that shadow synced session values.
        st.session_state.pop("_rn_ver", None)
        st.session_state.pop("_rn_dt", None)
    else:
        ss_default(key_ver, version)
        ss_default(key_date, doc_date)


def mark_release_doc_metadata_customized(prefix: str = "rn_", *, meta_prefix: str = "") -> None:
    """Remember that the user manually edited version/date fields."""
    key_custom = f"{meta_prefix}metadata_customized" if meta_prefix else "rn_metadata_customized"
    st.session_state[key_custom] = True


def ensure_ui_build_sync() -> bool:
    """Drop stale release-notes draft fields when the UI build changes."""
    prev = st.session_state.get("_ui_build_id")
    if prev == UI_BUILD_ID:
        return False

    for key in RN_DRAFT_RESET_KEYS:
        st.session_state.pop(key, None)
    st.session_state.pop("_rn_ver", None)
    st.session_state.pop("_rn_dt", None)
    st.session_state["_ui_build_id"] = UI_BUILD_ID
    return prev is not None


def ss_default(key: str, value) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def go(step: int) -> None:
    st.session_state["wiz_step"] = step
    st.rerun()


def ensure_deployer_wizard_version() -> bool:
    """Reset deployer session when step flow changes. Returns True if user was migrated."""
    current = st.session_state.get("wiz_wizard_version")
    if current == DEPLOYER_WIZARD_VERSION:
        return False

    for k in list(st.session_state.keys()):
        if k.startswith(("wiz_", "dep_", "paste_", "_prev_paste_")):
            del st.session_state[k]
    st.session_state["wiz_wizard_version"] = DEPLOYER_WIZARD_VERSION
    st.session_state["wiz_step"] = 1
    return current is not None


def collect_deploy_filled(proj_key: str, multi_client: bool) -> tuple[dict[str, dict], list[str]]:
    """Build deployment info from session state. Only includes entries with a deployment ID."""
    from datetime import datetime

    today_str = datetime.now().strftime("%B %d %Y")
    filled: dict[str, dict] = {}
    skipped: list[str] = []

    if multi_client:
        grouped = st.session_state.get("wiz_grouped", {})
        for client in grouped.keys():
            dep_id = st.session_state.get(f"dep_id_{client}", "").strip()
            dep_date = st.session_state.get(f"dep_date_{client}", "").strip()
            dep_time = st.session_state.get(f"dep_time_{client}", "").strip()
            if dep_id:
                filled[client] = {
                    "deployment_id": dep_id,
                    "deployment_date": dep_date or today_str,
                    "deployment_time": dep_time,
                }
            else:
                skipped.append(client)
    else:
        dep_id = st.session_state.get("dep_id_single", "").strip()
        dep_date = st.session_state.get("dep_date_single", "").strip() or today_str
        dep_time = st.session_state.get("dep_time_single", "").strip()
        if dep_id:
            filled[proj_key] = {
                "deployment_id": dep_id,
                "deployment_date": dep_date,
                "deployment_time": dep_time,
            }

    return filled, skipped


def deploy_filled_is_valid(filled: dict[str, dict]) -> bool:
    if not filled:
        return False
    return all(
        info.get("deployment_id", "").strip() and info.get("deployment_time", "").strip()
        for info in filled.values()
    )


def first_filled_entry(filled: dict[str, dict]) -> dict | None:
    """Return the first deployment-info dict, or None when ``filled`` is empty."""
    if not filled:
        return None
    return next(iter(filled.values()))


def resolve_grouped_client(client_label: str, grouped: dict[str, list]) -> str | None:
    """Match a deployment client label to a key in ``wiz_grouped`` (space-insensitive)."""
    if client_label in grouped:
        return client_label
    return jira_client.fuzzy_match_client(client_label, list(grouped.keys()))


def issues_for_filled_client(client_label: str, grouped: dict[str, list]) -> list[dict]:
    """Tickets for one filled client, resolving fuzzy client-name differences."""
    key = resolve_grouped_client(client_label, grouped)
    if not key:
        return []
    return grouped.get(key, [])


def save_deploy_filled_snapshot(proj_key: str, multi_client: bool) -> bool:
    """Persist deployment info from session state for Review/Deploy steps."""
    filled, skipped = collect_deploy_filled(proj_key, multi_client)
    if not deploy_filled_is_valid(filled):
        return False
    st.session_state["wiz_filled"] = filled
    st.session_state["wiz_skipped"] = skipped
    st.session_state["wiz_deploy_info_saved"] = True
    from session_persist import persist_deploy_draft, persist_session

    persist_deploy_draft(dict(st.session_state))
    persist_session(dict(st.session_state))
    return True


def get_deploy_filled_snapshot(proj_key: str, multi_client: bool) -> tuple[dict[str, dict], list[str]]:
    """Return saved deployment info, falling back to live session fields."""
    filled = st.session_state.get("wiz_filled", {})
    skipped = st.session_state.get("wiz_skipped", [])
    if deploy_filled_is_valid(filled):
        return filled, skipped
    return collect_deploy_filled(proj_key, multi_client)


def collect_release_notes_deploy_info(release_version: str | None = None) -> dict[str, dict]:
    """Merge deployer session + deployment history for release notes auto-fill."""
    from generators.release_notes_template_defaults import DEFAULT_DEPLOYMENT_STATUS

    merged: dict[str, dict] = {}

    filled = st.session_state.get("wiz_filled", {})
    if isinstance(filled, dict):
        for client, info in filled.items():
            if isinstance(info, dict) and info.get("deployment_id"):
                merged[str(client)] = {
                    **info,
                    "status": DEFAULT_DEPLOYMENT_STATUS,
                }

    proj_key = st.session_state.get("wiz_project", "")
    multi_client = False
    for proj in config.PROJECTS:
        if proj.get("key") == proj_key:
            multi_client = bool(proj.get("multi_client"))
            break
    live_filled, _ = collect_deploy_filled(proj_key, multi_client)
    for client, info in live_filled.items():
        if info.get("deployment_id"):
            merged[str(client)] = {**info, "status": DEFAULT_DEPLOYMENT_STATUS}

    for entry in load_history():
        if release_version and entry.get("version") != release_version:
            continue
        clients = entry.get("clients", {})
        if not isinstance(clients, dict):
            continue
        for client, info in clients.items():
            if not isinstance(info, dict) or not info.get("deployment_id"):
                continue
            if str(client) not in merged:
                merged[str(client)] = {
                    "deployment_id": info.get("deployment_id", ""),
                    "deployment_date": info.get("deployment_date", ""),
                    "deployment_time": info.get("deployment_time", ""),
                    "status": DEFAULT_DEPLOYMENT_STATUS,
                }
        if release_version:
            break

    return merged


def collect_deployer_prefill(
    grouped: dict[str, list],
    release_version: str | None = None,
) -> dict[str, dict]:
    """Deployment IDs sourced from session notes, SharePoint, and history."""
    import deploy_prefill

    grouped_keys = list(grouped.keys())
    prefill, source_labels = deploy_prefill.build_deploy_prefill(
        grouped_keys,
        deployment_row_text=st.session_state.get("rn_deployment_rows", ""),
        docx_bytes=st.session_state.get("rn_docx_bytes")
        if isinstance(st.session_state.get("rn_docx_bytes"), bytes)
        else None,
        sharepoint_url=str(
            st.session_state.get("shared_sharepoint_url")
            or st.session_state.get("stk_sharepoint")
            or ""
        ).strip(),
        release_version=release_version,
    )
    st.session_state["_deployer_prefill_source"] = ", ".join(source_labels)
    return prefill


def _add_deployment_row_sources(
    sources: dict[str, dict],
    rows: list[list[str]],
) -> None:
    """Merge deployment table rows into a client-keyed source map."""
    for row in rows:
        client = (row[0] or "").strip()
        if not client:
            continue
        parts = parse_deployment_id_time(row[3] if len(row) > 3 else "")
        if not parts.get("deployment_id"):
            continue
        if client not in sources:
            sources[client] = parts
            continue
        existing = sources[client]
        for field in ("deployment_id", "deployment_date", "deployment_time"):
            if not existing.get(field) and parts.get(field):
                existing[field] = parts[field]


def init_dep_field_defaults(client_names: list[str], today_str: str) -> None:
    """Ensure date defaults exist without conflicting Streamlit value= params."""
    for client in client_names:
        st.session_state.setdefault(f"dep_date_{client}", today_str)
    st.session_state.setdefault("dep_date_single", today_str)


def reset_wizard() -> None:
    clear_deployer_session(full_reset=True)
    st.rerun()


def clear_deployer_session(*, full_reset: bool = False) -> None:
    """Drop deployer wizard state (optionally reset step to 1)."""
    for k in list(st.session_state.keys()):
        if k.startswith(("wiz_", "dep_", "paste_", "_prev_paste_")):
            del st.session_state[k]
    st.session_state.pop("wiz_undo_data", None)
    st.session_state.pop("undo_confirm", None)
    st.session_state["wiz_wizard_version"] = DEPLOYER_WIZARD_VERSION
    if full_reset:
        st.session_state["wiz_step"] = 1


_APP_PREFIXES: dict[str, tuple[str, ...]] = {
    "ticket_review": ("tr_", "_tr_"),
    "release_notes": ("rn_", "_rn_"),
    "service_ticket": ("stk_", "_stk_"),
    "ai_ticket_creator": ("aitc_",),
}


def reset_app(app_id: str) -> None:
    prefixes = _APP_PREFIXES.get(app_id, ())
    for k in list(st.session_state.keys()):
        if any(k.startswith(p) for p in prefixes):
            del st.session_state[k]
    if app_id == "ticket_review":
        st.session_state.pop(_SNAPSHOT_KEY, None)
        _clear_drift_results()
    st.rerun()


def load_history() -> list[dict]:
    """Load deployment history; surface Streamlit errors on corrupt files."""
    path = _history_path()
    try:
        return deployment_history.load_history(path)
    except deployment_history.HistoryLoadError as exc:
        st.error(str(exc), icon=":material/error:")
        return []


def save_history(entry: dict) -> None:
    deployment_history.save_history(entry, path=_history_path())


def mark_history_entry_reverted(timestamp: str) -> None:
    """Mark a deployment history record as undone."""
    deployment_history.mark_history_entry_reverted(timestamp, path=_history_path())

def save_and_reload_env(
    email: str,
    token: str,
    base_url: str | None = None,
    workspace: str | None = None,
) -> None:
    from release_platform.ui.env_config import save_and_reload_env as _save

    _save(email, token, base_url=base_url, workspace=workspace)


def persist_workspace_to_env(workspace: str) -> None:
    from release_platform.ui.env_config import persist_workspace_to_env as _persist

    _persist(workspace)


def normalize_version_id(version_id: str | int | None) -> str:
    """Coerce Jira fix-version ids to a stable string for comparisons and cache keys."""
    return str(version_id or "").strip()


def normalize_version_record(version: dict) -> dict:
    """Return a copy of a Jira version dict with a string ``id``."""
    out = dict(version)
    if out.get("id") is not None:
        out["id"] = normalize_version_id(out["id"])
    return out


def ticket_issues_cache_key(
    project_key: str,
    version_id: str | int,
    *,
    prefix: str = "_tr_issues_",
) -> str:
    """Session cache key for scoped version issue lists."""
    version_id = normalize_version_id(version_id)
    fp = ""
    try:
        scope = team_scope.ensure_scope_ready(project_key)
        resolved = team_scope.resolve_filter_id(scope)
        fp = team_scope.scope_fingerprint(project_key, scope, resolved_filter_id=resolved)
    except team_scope.TeamScopeError:
        fp = "unscoped"
    return f"{prefix}{project_key}_{version_id}_{fp}"


def scope_fingerprint_for_project(project_key: str) -> str:
    try:
        scope = team_scope.ensure_scope_ready(project_key)
        resolved = team_scope.resolve_filter_id(scope)
        return team_scope.scope_fingerprint(project_key, scope, resolved_filter_id=resolved)
    except team_scope.TeamScopeError:
        return ""


def projects_blocking_scope() -> list[str]:
    return team_scope.projects_missing_scope()


def workflow_blocked_by_scope() -> tuple[bool, list[str]]:
    missing = projects_blocking_scope()
    return bool(missing), missing


def get_project_cfg(key: str) -> dict | None:
    """Return project config for the given key, or None if not found."""
    for p in config.PROJECTS:
        if p["key"] == key:
            return p
    return None


def load_versions_cached(cache_key: str, project_key: str) -> list[dict]:
    if cache_key not in st.session_state:
        try:
            with st.spinner(f"Loading {project_key} releases\u2026"):
                versions = jira_client.get_project_versions(project_key, released=False)
                st.session_state[cache_key] = [
                    v for v in versions
                    if v.get("name", "").strip().lower() not in INITIAL_RELEASE_NAMES
                ]
        except Exception as exc:
            st.error(f"Failed to load {project_key} releases: {exc}")
            st.session_state[cache_key] = []
    return st.session_state[cache_key]


# ── Shared cross-app state (dynamic project keys) ────────────────


_SHARED_VERSIONS_PREFIX = "_shared_versions_"


def _shared_release_keys() -> list[str]:
    """Return the session-state keys for shared release selections."""
    return [f"shared_release_{p['key']}" for p in config.PROJECTS]


def load_shared_versions(project_key: str) -> list[dict]:
    cache_key = f"{_SHARED_VERSIONS_PREFIX}{project_key}"
    return load_versions_cached(cache_key, project_key)


def _app_release_key(prefix: str, project_key: str) -> str:
    return f"{prefix}release_{project_key}"


def populate_from_shared(prefix: str) -> bool:
    populated = False
    for proj in config.PROJECTS:
        pk = proj["key"]
        app_key = _app_release_key(prefix, pk)
        shared_key = f"shared_release_{pk}"
        if not st.session_state.get(app_key) and st.session_state.get(shared_key):
            version = normalize_version_record(st.session_state[shared_key])
            st.session_state[app_key] = version
            st.session_state[shared_key] = version
            populated = True
    return populated


_DRIFT_GATE_PREFIXES = ("rn", "stk")
_DRIFT_GATE_SUFFIXES = ("drift_result", "drift_ack", "continue_pending")
_DRIFT_RESULT_KEYS = tuple(
    f"_{prefix}_{suffix}"
    for prefix in _DRIFT_GATE_PREFIXES
    for suffix in _DRIFT_GATE_SUFFIXES
)


def _clear_drift_results() -> None:
    for key in _DRIFT_RESULT_KEYS:
        st.session_state.pop(key, None)


def clear_shared_release(prefix: str, project_key: str) -> None:
    """Clear release selection for one project and any cached issue lists."""
    sel_key = _app_release_key(prefix, project_key)
    had_selection = bool(st.session_state.get(sel_key))
    st.session_state.pop(sel_key, None)
    st.session_state.pop(f"shared_release_{project_key}", None)
    if had_selection:
        st.session_state.pop("shared_snapshot", None)
        _clear_drift_results()
    for k in list(st.session_state.keys()):
        if k.startswith(f"_tr_issues_{project_key}_"):
            del st.session_state[k]


def write_shared_release(prefix: str, project_key: str, version: dict) -> bool:
    """Persist a release pick. Returns True when the version id actually changed."""
    version = normalize_version_record(version)
    sel_key = _app_release_key(prefix, project_key)
    prev_id = normalize_version_id(st.session_state.get(sel_key, {}).get("id"))
    new_id = normalize_version_id(version.get("id"))
    st.session_state[sel_key] = version
    st.session_state[f"shared_release_{project_key}"] = version
    if prev_id == new_id:
        return False
    st.session_state.pop("shared_snapshot", None)
    _clear_drift_results()
    for k in list(st.session_state.keys()):
        if k.startswith(f"_tr_issues_{project_key}_"):
            del st.session_state[k]
    return True


def _release_option_label(version: dict) -> str:
    name = version.get("name", version.get("id", ""))
    desc = (version.get("description") or "").strip()
    return f"{name} — {desc}" if desc else str(name)


def _apply_release_selection(
    prefix: str,
    project_key: str,
    version_id: str | int | None,
    versions_by_id: dict[str, dict],
    on_change_keys: tuple[str, ...],
) -> bool:
    """Update release selection when the chosen version id changed."""
    sel_key = _app_release_key(prefix, project_key)
    picked_id = normalize_version_id(version_id)
    current_id = normalize_version_id(st.session_state.get(sel_key, {}).get("id"))
    if picked_id == current_id:
        return False

    if picked_id:
        changed = write_shared_release(prefix, project_key, versions_by_id[picked_id])
    else:
        clear_shared_release(prefix, project_key)
        changed = True

    if changed:
        for k in on_change_keys:
            st.session_state.pop(k, None)
    return changed


def render_project_release_picker(
    prefix: str,
    *,
    button_key_prefix: str,
    on_change_keys: tuple[str, ...] = (),
) -> None:
    """Render per-project release dropdowns with clear / change / deselect support."""
    any_selected = False

    for proj in config.PROJECTS:
        pk = proj["key"]
        versions = load_shared_versions(pk)
        sel_key = _app_release_key(prefix, pk)
        current_id = normalize_version_id(st.session_state.get(sel_key, {}).get("id"))
        if current_id:
            any_selected = True

        hdr_l, hdr_r = st.columns([5, 1])
        box_key = f"{button_key_prefix}_box_{pk}"
        sync_key = f"_{button_key_prefix}_sync_{pk}"
        with hdr_l:
            st.markdown(f"### {pk} Project")
        with hdr_r:
            if current_id and st.button(
                "Clear",
                key=f"{button_key_prefix}_clr_{pk}",
                use_container_width=True,
            ):
                if _apply_release_selection(prefix, pk, "", {}, on_change_keys):
                    st.session_state.pop(box_key, None)
                    st.session_state.pop(sync_key, None)
                    st.rerun()

        if not versions:
            st.info(f"No unreleased versions found for {pk}.")
            continue

        versions_by_id = {normalize_version_id(v["id"]): normalize_version_record(v) for v in versions}
        option_ids = [""] + list(versions_by_id.keys())
        option_labels = {"": "— None —"}
        option_labels.update(
            {vid: _release_option_label(versions_by_id[vid]) for vid in versions_by_id}
        )

        expected = current_id if current_id in option_ids else ""
        if st.session_state.get(sync_key) != current_id:
            st.session_state[box_key] = expected
            st.session_state[sync_key] = current_id

        selected_id = st.selectbox(
            f"{pk} release",
            options=option_ids,
            format_func=lambda vid: option_labels[vid],
            key=box_key,
            help="Pick a release, switch to another, or choose '— None —' to deselect.",
        )

        if _apply_release_selection(
            prefix, pk, selected_id, versions_by_id, on_change_keys
        ):
            st.rerun()

        if current_id:
            chosen = versions_by_id.get(current_id, {})
            st.caption(f"Selected: **{esc(chosen.get('name', current_id))}**")

    if any_selected:
        if st.button(
            "Clear all releases",
            key=f"{button_key_prefix}_clear_all",
            type="secondary",
        ):
            for proj in config.PROJECTS:
                pk = proj["key"]
                clear_shared_release(prefix, pk)
                st.session_state.pop(f"{button_key_prefix}_box_{pk}", None)
                st.session_state.pop(f"_{button_key_prefix}_sync_{pk}", None)
            for k in on_change_keys:
                st.session_state.pop(k, None)
            st.rerun()


def navigate_to_app(app_id: str, *, reset: bool = False) -> None:
    """Switch active app without wiping in-progress session state unless ``reset`` is True."""
    if reset:
        prefixes = _APP_PREFIXES.get(app_id, ())
        for k in list(st.session_state.keys()):
            if any(k.startswith(p) for p in prefixes):
                del st.session_state[k]
    st.session_state["active_app"] = app_id
    st.rerun()


def get_shared_release_summary() -> str | None:
    parts = []
    for proj in config.PROJECTS:
        pk = proj["key"]
        rel = st.session_state.get(f"shared_release_{pk}")
        if rel:
            parts.append(f"{pk}: {rel.get('name', '?')}")
    return " + ".join(parts) if parts else None


# ── Ticket snapshot / lock-in ─────────────────────────────────────

_SNAPSHOT_KEY = "shared_snapshot"


def create_snapshot(
    issues: list[dict],
    *,
    candidate_keys: set[str] | None = None,
) -> dict:
    """Lock the approved ticket list.

    ``candidate_keys`` is every ticket that was on the fix version when the user
    made the selection. Whatever they deselected is stored as ``excluded_keys``
    so later drift checks don't report those tickets as new arrivals.
    """
    from datetime import datetime

    releases = {}
    for proj in config.PROJECTS:
        pk = proj["key"]
        rel = st.session_state.get(f"shared_release_{pk}", {})
        if rel:
            releases[f"release_{pk}"] = rel

    ticket_keys = sorted(iss["key"] for iss in issues)
    scope_fingerprints = team_scope.collect_scope_fingerprints()
    snapshot = {
        "locked_at": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        **releases,
        "ticket_keys": ticket_keys,
        "excluded_keys": sorted(set(candidate_keys or set()) - set(ticket_keys)),
        "issues": issues,
        "scope_fingerprints": scope_fingerprints,
        "selection_mode": st.session_state.get("tr_selection_mode", "fix_version"),
    }
    if snapshot["selection_mode"] == "status":
        from release_platform.ui.ticket_review.selection import get_selected_statuses

        snapshot["status_filters"] = {
            proj["key"]: get_selected_statuses(proj["key"])
            for proj in config.PROJECTS
            if get_selected_statuses(proj["key"])
        }
    from release_platform.ui.ticket_review.jira_team_filter import team_filters_for_snapshot

    team_snapshot = team_filters_for_snapshot()
    if team_snapshot:
        snapshot["jira_team_filters"] = team_snapshot
    st.session_state[_SNAPSHOT_KEY] = snapshot
    return snapshot


def get_snapshot_excluded_keys() -> set[str]:
    """Tickets the user deliberately deselected during Ticket Review."""
    snap = get_snapshot()
    if not snap:
        return set()
    if "excluded_keys" in snap:
        return set(snap["excluded_keys"])

    # Snapshot locked before exclusions were recorded — recover the deselected
    # tickets from the Ticket Review issue cache still held in this session.
    locked = set(snap.get("ticket_keys", []))
    cached = {iss["key"] for iss in collect_cached_ticket_review_issues()}
    recovered = sorted(cached - locked)
    snap["excluded_keys"] = recovered
    return set(recovered)


def get_snapshot_qa_excluded_keys() -> set[str]:
    snap = get_snapshot()
    if not snap:
        return set()
    return {str(key).strip().upper() for key in (snap.get("qa_excluded_keys") or []) if str(key).strip()}


def effective_snapshot_ticket_keys(snap: dict | None = None) -> set[str] | None:
    """Locked ticket keys minus post-QA exclusions."""
    snap = snap if snap is not None else get_snapshot()
    if not snap:
        return None
    keys = {str(key).strip().upper() for key in (snap.get("ticket_keys") or []) if str(key).strip()}
    if not keys:
        return None
    qa_excluded = {
        str(key).strip().upper()
        for key in (snap.get("qa_excluded_keys") or [])
        if str(key).strip()
    }
    return keys - qa_excluded


def filter_snapshot_issues(snap: dict | None = None) -> list[dict]:
    """Return snapshot issues limited to effective release ticket keys."""
    snap = snap if snap is not None else get_snapshot()
    if not snap:
        return []
    issues = list(snap.get("issues") or [])
    allowed = effective_snapshot_ticket_keys(snap)
    if allowed is None:
        return issues
    return [issue for issue in issues if str(issue.get("key") or "").strip().upper() in allowed]


def get_snapshot() -> dict | None:
    return st.session_state.get(_SNAPSHOT_KEY)


def get_snapshot_ticket_keys() -> set[str] | None:
    snap = get_snapshot()
    if not snap:
        return None
    return set(snap.get("ticket_keys", []))


def snapshot_selection_pending(selected_keys: set[str]) -> bool:
    """True when checkbox selection differs from the locked Ticket Review snapshot."""
    locked = get_snapshot_ticket_keys()
    if locked is None:
        return False
    return locked != selected_keys


def clear_ticket_review_lock() -> None:
    """Drop the locked snapshot only — stay on Ticket Review Step 2."""
    st.session_state.pop(_SNAPSHOT_KEY, None)
    try:
        from session_persist import persist_session

        persist_session(dict(st.session_state))
    except Exception:
        logger.debug("Could not persist after clearing ticket review lock", exc_info=True)


def collect_cached_ticket_review_issues() -> list[dict]:
    """Return merged issue lists cached by Ticket Review step 2, if any."""
    from release_platform.ui.ticket_review.jira_team_filter import team_filter_cache_suffix
    from release_platform.ui.ticket_review.selection import (
        MODE_STATUS,
        get_selected_statuses,
        get_selection_mode,
        status_issues_cache_key,
    )

    issues: list[dict] = []
    seen: set[str] = set()
    mode = get_selection_mode()
    for proj in config.PROJECTS:
        pk = proj["key"]
        if mode == MODE_STATUS:
            statuses = tuple(sorted(get_selected_statuses(pk)))
            if not statuses:
                continue
            base_key = status_issues_cache_key(pk, statuses)
            cache_key = f"{base_key}_{team_filter_cache_suffix(pk)}"
        else:
            rel = st.session_state.get(f"shared_release_{pk}") or st.session_state.get(
                f"tr_release_{pk}", {}
            )
            if not rel:
                continue
            base_key = ticket_issues_cache_key(pk, rel["id"])
            cache_key = f"{base_key}_{team_filter_cache_suffix(pk)}"
        cached = st.session_state.get(cache_key, [])
        if not cached:
            cached = st.session_state.get(base_key, [])
        for iss in cached:
            key = iss.get("key")
            if key and key not in seen:
                seen.add(key)
                issues.append(iss)
    return issues


def lock_pending_ticket_review() -> dict[str, object]:
    """Create snapshot from Ticket Review session when user skipped lock-in click."""
    if get_snapshot_ticket_keys():
        return {"ok": True, "count": len(get_snapshot_ticket_keys() or []), "message": "Already locked."}

    selected = set(st.session_state.get("tr_selected_keys") or [])
    issues = collect_cached_ticket_review_issues()
    candidate_keys = {iss["key"] for iss in issues}
    if not issues:
        return {
            "ok": False,
            "count": 0,
            "message": "No Ticket Review ticket list in this session. Open Ticket Review first.",
        }

    if selected:
        issues = [iss for iss in issues if iss["key"] in selected]
    if not issues:
        return {
            "ok": False,
            "count": 0,
            "message": "Selected tickets not found. Return to Ticket Review and refresh.",
        }

    snap = create_snapshot(issues, candidate_keys=candidate_keys)
    return {
        "ok": True,
        "count": len(snap.get("ticket_keys", [])),
        "message": f"Locked {len(snap.get('ticket_keys', []))} tickets.",
    }


def check_snapshot_scope_drift() -> dict | None:
    """Return drift info when project scope changed since snapshot lock."""
    snap = get_snapshot()
    if not snap:
        return None
    stored = snap.get("scope_fingerprints") or {}
    matches, changed = team_scope.snapshot_scope_matches(stored)
    if matches:
        return None
    return {
        "status": "scope_changed",
        "changed_projects": changed,
        "message": (
            "Team scope changed since Ticket Review was locked. "
            f"Refresh tickets for: {', '.join(changed)}."
        ),
    }


from release_platform.ui.snapshot_ops import fetch_issues_for_snapshot, snapshot_selection_mode


def check_snapshot_drift() -> dict | None:
    """Compare locked snapshot tickets to the current Jira source (fix version or status).

    Returns ``None`` when no snapshot exists.

    Tickets deselected during Ticket Review are not drift — they stay on the
    source by design, so they are ignored here.

    Otherwise returns a dict with ``status``:
    - ``ok`` — locked list matches Jira
    - ``drift`` — added/removed ticket keys (see ``added``, ``removed``)
    - ``error`` — Jira API failed; callers must block proceed (fail closed)
    """
    snap = get_snapshot()
    if not snap:
        return None

    scope_drift = check_snapshot_scope_drift()
    if scope_drift:
        return scope_drift

    mode = snapshot_selection_mode(snap)
    if mode == "status" and not (snap.get("status_filters") or {}):
        return {
            "status": "error",
            "message": (
                "Status-only snapshot is missing status filters. "
                "Re-lock tickets in Ticket Review."
            ),
            "added": [],
            "removed": [],
        }

    try:
        current_keys = [iss["key"] for iss in fetch_issues_for_snapshot(snap) if iss.get("key")]
    except Exception as exc:
        logger.debug("Failed to fetch issue keys for drift check", exc_info=True)
        return {
            "status": "error",
            "message": str(exc),
            "added": [],
            "removed": [],
        }

    if mode != "status":
        has_release = any(snap.get(f"release_{proj['key']}", {}) for proj in config.PROJECTS)
        if not has_release and not current_keys:
            return {"status": "ok", "added": [], "removed": []}

    locked = set(snap["ticket_keys"])
    current = set(current_keys)
    excluded = get_snapshot_excluded_keys()
    added = sorted(current - locked - excluded)
    removed = sorted(locked - current)

    if added or removed:
        return {"status": "drift", "added": added, "removed": removed}
    return {"status": "ok", "added": [], "removed": []}


def drift_blocks_proceed(drift: dict | None) -> bool:
    """True when drift check failed and the user must not continue."""
    return bool(drift and drift.get("status") in {"error", "scope_changed"})


def drift_has_changes(drift: dict | None) -> bool:
    """True when Jira ticket set differs from the locked snapshot."""
    return bool(drift and drift.get("status") == "drift")


def relock_snapshot(*, keep_exclusions: bool = True) -> dict:
    """Re-fetch the locked source (fix version or status filters) and lock again.

    Previously deselected tickets stay out unless ``keep_exclusions`` is False;
    re-locking is meant to pick up genuinely new tickets, not to silently undo
    the user's Ticket Review choices.
    """
    snap = get_snapshot()
    if not snap:
        return create_snapshot([])

    all_issues = fetch_issues_for_snapshot(snap)
    candidate_keys = {iss["key"] for iss in all_issues}
    excluded = get_snapshot_excluded_keys() if keep_exclusions else set()
    kept = [iss for iss in all_issues if iss["key"] not in excluded]

    new_snap = create_snapshot(kept, candidate_keys=candidate_keys)
    if snapshot_selection_mode(snap) == "status":
        new_snap["selection_mode"] = "status"
        new_snap["status_filters"] = dict(snap.get("status_filters") or {})
    if snap.get("jira_team_filters"):
        new_snap["jira_team_filters"] = dict(snap["jira_team_filters"])
    st.session_state[_SNAPSHOT_KEY] = new_snap
    return new_snap


def _drift_signature(drift: dict) -> str:
    return "|".join(sorted(drift.get("added", []) + drift.get("removed", [])))


def _render_drift_gate(key_prefix: str) -> bool:
    """Render the drift check UI. Returns True when it is safe to continue."""
    drift_key = f"_{key_prefix}_drift_result"
    ack_key = f"_{key_prefix}_drift_ack"

    if drift_key not in st.session_state:
        with st.spinner("Checking for ticket changes in Jira\u2026"):
            st.session_state[drift_key] = check_snapshot_drift()

    drift = st.session_state[drift_key]

    if drift_blocks_proceed(drift):
        st.error(
            "**Cannot verify ticket list with Jira.**\n\n"
            f"{esc(drift.get('message', 'Unknown error'))}\n\n"
            "Proceeding without verification could use a stale ticket list. "
            "Check your network and Jira access, then retry."
        )
        if st.button("Retry drift check", key=f"{key_prefix}_retry_drift"):
            st.session_state.pop(drift_key, None)
            st.rerun()
        return False

    if not drift_has_changes(drift):
        return True

    signature = _drift_signature(drift)
    if st.session_state.get(ack_key) == signature:
        return True

    parts = []
    if drift.get("added"):
        parts.append(f"**{len(drift['added'])} added:** {', '.join(drift['added'])}")
    if drift.get("removed"):
        parts.append(f"**{len(drift['removed'])} removed:** {', '.join(drift['removed'])}")

    st.warning(
        "**New tickets appeared in Jira since lock-in.**\n\n"
        + "\n\n".join(parts)
        + "\n\nTickets you deselected in Ticket Review are not listed here. "
        "Choose how to proceed:"
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Add them and re-lock", key=f"{key_prefix}_relock"):
            with st.spinner("Re-fetching tickets\u2026"):
                relock_snapshot()
            st.session_state.pop(drift_key, None)
            st.session_state.pop(ack_key, None)
            st.rerun()
    with c2:
        if st.button("Proceed with locked list", key=f"{key_prefix}_proceed_stale"):
            st.session_state[ack_key] = signature
            return True

    return False


def scope_restore_blocks_proceed() -> bool:
    """True when restored draft had team scope drift and user has not reconciled."""
    return bool(st.session_state.get("_scope_restore_blocked"))


def render_scope_restore_gate(key_prefix: str) -> bool:
    """Block proceed until Ticket Review re-lock or explicit acknowledge."""
    if not scope_restore_blocks_proceed():
        return True
    changed = st.session_state.get("_scope_restore_changed") or []
    detail = ", ".join(changed) if changed else "team scope"
    st.error(
        f"**Team scope changed** since this session was saved ({detail}). "
        "Re-lock tickets in Ticket Review before continuing, or acknowledge below."
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Open Ticket Review", key=f"{key_prefix}_scope_goto_tr"):
            navigate_to_app("ticket_review")
    with c2:
        if st.button("Acknowledge and proceed", key=f"{key_prefix}_scope_ack"):
            st.session_state.pop("_scope_restore_blocked", None)
            st.session_state.pop("_scope_restore_changed", None)
            st.session_state.pop("_draft_scope_warning", None)
            return True
    return False


def continue_with_drift_gate(key_prefix: str, *, clicked: bool) -> bool:
    """Gate a Continue action behind the lock-in drift check.

    The gate stays open across reruns so its buttons remain clickable — a
    Streamlit button is only True on the run it is clicked, so rendering the
    gate inline with the Continue click would discard the user's choice.
    """
    pending_key = f"_{key_prefix}_continue_pending"
    if clicked:
        st.session_state[pending_key] = True
    if not st.session_state.get(pending_key):
        return False

    if not render_scope_restore_gate(key_prefix):
        return False

    if _render_drift_gate(key_prefix):
        st.session_state.pop(pending_key, None)
        return True
    return False


def get_snapshot_included_keys_for_project(proj_key: str) -> set[str] | None:
    """Return ticket keys included in the shared snapshot for one project, or None if unavailable."""
    snap = get_snapshot()
    if not snap:
        return None
    if not snap.get(f"release_{proj_key}"):
        return None
    prefix = f"{proj_key.upper()}-"
    return {
        key
        for key in snap.get("ticket_keys", [])
        if str(key).upper().startswith(prefix)
    }


def get_snapshot_keys_for_release(proj_key: str, release_id: str) -> set[str] | None:
    """Snapshot ticket keys when the snapshot matches this project + release version."""
    snap = get_snapshot()
    if not snap:
        return None
    rel = snap.get(f"release_{proj_key}", {})
    if not rel or str(rel.get("id")) != str(release_id):
        return None
    return get_snapshot_included_keys_for_project(proj_key)


def apply_deploy_issue_filter(
    issues: list[dict],
    proj_key: str,
    release: dict,
) -> tuple[list[dict], dict]:
    """Keep only tickets approved in Ticket Review snapshot for this release."""
    from release_platform.ui.workflow import is_deployer_standalone

    if is_deployer_standalone():
        return issues, {
            "using_snapshot": False,
            "standalone": True,
            "removed": [],
            "missing_from_release": [],
        }

    release_id = str(release.get("id", ""))
    approved = get_snapshot_keys_for_release(proj_key, release_id)
    if approved is None:
        return issues, {
            "using_snapshot": False,
            "removed": [],
            "missing_from_release": [],
        }

    qa_excluded = get_snapshot_qa_excluded_keys()
    approved = {key for key in approved if key.upper() not in qa_excluded}

    on_release = {iss["key"] for iss in issues}
    filtered = [iss for iss in issues if iss["key"] in approved]
    return filtered, {
        "using_snapshot": True,
        "removed": sorted(on_release - approved),
        "missing_from_release": sorted(approved - on_release),
    }


def rebuild_wiz_grouped(issues: list[dict], proj_key: str) -> dict[str, list[dict]] | None:
    proj_cfg = get_project_cfg(proj_key)
    if not proj_cfg or not proj_cfg.get("multi_client"):
        return None
    return jira_client.group_issues_by_client(issues, project_key=proj_key)


def render_deploy_filter_warnings(meta: dict, release_name: str) -> None:
    """Show snapshot vs fix-version mismatches before deploy."""
    if meta.get("standalone"):
        st.info(
            "**Quick start** — all tickets on this fix version are eligible. "
            "On **Review**, uncheck any ticket that failed in production; the rest "
            "will receive deployment comments and transition to Done."
        )
        return

    if not meta.get("using_snapshot"):
        st.info(
            "No Ticket Review snapshot for this release — **all tickets on the fix version** "
            "will be eligible to deploy. Run Ticket Review first to lock the correct ticket list."
        )
        return

    if meta.get("missing_from_release"):
        keys = ", ".join(f"**{k}**" for k in meta["missing_from_release"])
        st.error(
            f"Ticket Review selected {keys}, but they are **not on fix version {release_name}** "
            f"in Jira. Fix the fix version on those tickets in Jira, or update your release selection."
        )

    if meta.get("removed"):
        keys = ", ".join(f"**{k}**" for k in meta["removed"])
        st.warning(
            f"Excluded from deploy (on fix version but not in Ticket Review): {keys}. "
            "On **Exclude Tickets**, they are pre-selected — choose "
            "**Exclude selected & continue** to remove their fix version."
        )


def invalidate_snapshot_if_selection_changed(selected_keys: set[str]) -> None:
    """Legacy helper — prefer ``snapshot_selection_pending`` + explicit re-lock."""
    snap = get_snapshot()
    if not snap:
        return
    if set(snap.get("ticket_keys", [])) != selected_keys:
        st.session_state.pop(_SNAPSHOT_KEY, None)
        _clear_drift_results()


def deploy_filter_blocks_progress(meta: dict) -> bool:
    """True when snapshot/fix-version mismatch must block deployer progress."""
    return bool(meta.get("missing_from_release"))


def compute_deploy_run_fingerprint(
    release_id: str | int | None,
    selected_keys: set[str] | list[str],
    filled: dict,
    *,
    force_deploy: bool = False,
) -> str:
    """Hash deploy inputs so cached step-6 results invalidate when inputs change."""
    import hashlib

    payload = {
        "release_id": str(release_id or ""),
        "selected_keys": sorted(selected_keys),
        "filled": filled,
        "force_deploy": force_deploy,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def clear_deploy_results_cache(release_id: str | int | None = None) -> None:
    """Drop cached deploy/undo results (all releases or one release id)."""
    rid = str(release_id) if release_id is not None else None
    for k in list(st.session_state.keys()):
        if rid is None:
            if k.startswith((
                "wiz_results_",
                "wiz_results_fp_",
                "wiz_undo_results_",
                "wiz_deploy_execute_confirmed_",
            )):
                st.session_state.pop(k, None)
        else:
            if k in (
                f"wiz_results_{rid}",
                f"wiz_results_fp_{rid}",
                f"wiz_undo_results_{rid}",
                f"wiz_deploy_execute_confirmed_{rid}",
            ):
                st.session_state.pop(k, None)
    st.session_state.pop("wiz_undo_data", None)
    st.session_state.pop("undo_confirm", None)


def reset_deployer_downstream_state(*, clear_snapshot: bool = False) -> None:
    """Clear deployer wizard state below release selection."""
    for k in list(st.session_state.keys()):
        if k.startswith((
            "wiz_issues_",
            "wiz_exc_chk_",
            "wiz_dep_chk_",
            "wiz_results_",
            "wiz_results_fp_",
            "wiz_undo_results_",
        )):
            st.session_state.pop(k, None)
        if k.startswith(("dep_", "paste_", "_prev_paste_")):
            st.session_state.pop(k, None)
    for key in (
        "wiz_grouped",
        "wiz_issues",
        "wiz_deploy_filter_meta",
        "wiz_exc_initialized",
        "wiz_exc_selected_keys",
        "wiz_exc_confirm",
        "wiz_exc_issue_fp",
        "wiz_deploy_selected_keys",
        "wiz_deploy_issue_fp",
        "wiz_filled",
        "wiz_removed_from_release",
        "wiz_undo_data",
        "undo_confirm",
    ):
        st.session_state.pop(key, None)
    if clear_snapshot:
        st.session_state.pop(_SNAPSHOT_KEY, None)
        _clear_drift_results()


def apply_shared_release_to_deployer() -> bool:
    """Map ``shared_release_{PK}`` into deployer step-1 session keys."""
    proj_idx = st.session_state.get("wiz_project_idx", 0)
    if proj_idx >= len(config.PROJECTS):
        return False
    proj_key = config.PROJECTS[proj_idx]["key"]
    shared = st.session_state.get(f"shared_release_{proj_key}")
    if not shared:
        return False
    st.session_state["wiz_release_id"] = shared["id"]
    st.session_state["wiz_release"] = shared
    st.session_state["wiz_project"] = proj_key
    return True


def sync_rn_ticket_draft(selected_keys: set[str]) -> None:
    """Drop generated RN draft content when the ticket selection changes."""
    fp = "|".join(sorted(selected_keys))
    if st.session_state.get("rn_ticket_fp") == fp:
        return
    st.session_state["rn_ticket_fp"] = fp
    for key in RN_TICKET_DRAFT_KEYS:
        st.session_state.pop(key, None)


def invalidate_stk_plans() -> None:
    for key in STK_PLAN_KEYS:
        st.session_state.pop(key, None)
    st.session_state.pop("stk_plan_extracted_fp", None)


def sync_stk_release_defaults() -> None:
    """Refresh TCKT summary/schedule when the selected release changes."""
    uses_fix_version = service_ticket_uses_fix_version("stk_")
    fp = release_selection_fingerprint("stk_") if uses_fix_version else "status-only"
    if st.session_state.get("stk_release_fp") == fp:
        return
    for widget_key in (
        "_stk_summary",
        "_stk_psd",
        "_stk_pst",
        "_stk_ped",
        "_stk_pet",
        "_stk_sched_tz",
        "_stk_group_multiselect",
    ):
        st.session_state.pop(widget_key, None)
    st.session_state["stk_release_fp"] = fp

    version_name = ""
    if uses_fix_version:
        version_parts = []
        for proj in config.PROJECTS:
            rel = st.session_state.get(f"stk_release_{proj['key']}", {})
            if rel:
                version_parts.append(rel.get("name", ""))
        version_label, _ = derive_release_doc_metadata("stk_")
        if not version_label:
            unique = list(dict.fromkeys(p for p in version_parts if p))
            version_label = unique[0] if len(unique) == 1 else " + ".join(unique)
            if version_label and not str(version_label).lower().startswith("v"):
                version_label = f"v{version_label}"
        version_name = version_label

    try:
        import shipit_reference as sr

        st.session_state["stk_summary"] = sr.build_shipit_summary(version_name=version_name)
    except Exception:
        if version_name:
            st.session_state["stk_summary"] = (
                f"Glofox Insights Customize BI - Prod Deployment - Release Version "
                f"{str(version_name).lstrip('vV')}"
            )
        else:
            st.session_state["stk_summary"] = (
                "Glofox Insights Customize BI - Prod Deployment"
            )

    if uses_fix_version:
        release_date = None
        for proj in config.PROJECTS:
            rel = st.session_state.get(f"stk_release_{proj['key']}", {})
            parsed = parse_fix_version_date(rel.get("name", ""))
            if parsed:
                release_date = parsed
                break
        if release_date is None:
            release_date = datetime.now().date()

        from datetime import time as dt_time

        import release_defaults as rd

        sched = rd.default_deployment_schedule()
        st.session_state["stk_planned_start_date"] = release_date
        st.session_state["stk_planned_start_time"] = sched["start_time"]
        st.session_state["stk_planned_end_date"] = release_date
        st.session_state["stk_planned_end_time"] = sched["end_time"]
        st.session_state["stk_schedule_tz"] = (
            sched.get("source_timezone") or sched["timezone_name"] or config.TCKT_SCHEDULE_SOURCE_TZ
        )
    invalidate_stk_plans()


def sync_stk_plans_fingerprint() -> None:
    """Invalidate generated plans when tickets or the deployment window change."""
    extracted = st.session_state.get("stk_extracted", [])
    schedule_fp = "|".join(
        str(st.session_state.get(key, ""))
        for key in (
            "stk_planned_start_date",
            "stk_planned_start_time",
            "stk_planned_end_date",
            "stk_planned_end_time",
            "stk_schedule_tz",
        )
    )
    fp = "|".join(sorted(e.get("ticket", "") for e in extracted)) + "#" + schedule_fp
    if st.session_state.get("stk_plan_extracted_fp") == fp:
        return
    st.session_state["stk_plan_extracted_fp"] = fp
    invalidate_stk_plans()


def reset_deploy_selection_for_issues(issues: list[dict]) -> None:
    fp = "|".join(sorted(iss["key"] for iss in issues))
    if st.session_state.get("wiz_deploy_issue_fp") == fp:
        return
    st.session_state["wiz_deploy_issue_fp"] = fp
    st.session_state.pop("wiz_deploy_selected_keys", None)
    for k in list(st.session_state.keys()):
        if k.startswith("wiz_dep_chk_"):
            st.session_state.pop(k, None)


def reset_exclude_selection_for_issues(
    issues: list[dict],
    proj_key: str,
    release_id: str,
) -> None:
    fp = f"{proj_key}:{release_id}:|" + "|".join(sorted(iss["key"] for iss in issues))
    if st.session_state.get("wiz_exc_issue_fp") == fp:
        return
    st.session_state["wiz_exc_issue_fp"] = fp
    st.session_state.pop("wiz_exc_initialized", None)
    st.session_state.pop("wiz_exc_selected_keys", None)
    st.session_state.pop("wiz_exc_confirm", None)
    for k in list(st.session_state.keys()):
        if k.startswith("wiz_exc_chk_"):
            st.session_state.pop(k, None)


def validate_workspace_projects(projects: list[dict]) -> list[str]:
    errors: list[str] = []
    if not projects:
        errors.append("At least one project is required.")
        return errors
    seen: set[str] = set()
    for proj in projects:
        key = (proj.get("key") or "").strip().upper()
        if not key:
            errors.append("Project key cannot be empty.")
        elif key in seen:
            errors.append(f"Duplicate project key: {key}")
        else:
            seen.add(key)
        scope = team_scope.parse_scope(proj.get("scope"))
        scope_errors = team_scope.validate_scope_structure(scope, project_key=key)
        for err in scope_errors:
            errors.append(f"{key or 'Project'} scope: {err}")
    return errors


def get_default_exclusion_keys(
    issues: list[dict],
    proj_key: str,
    release_id: str,
) -> set[str]:
    """Tickets on the release fix version but excluded from the Ticket Review snapshot."""
    included = get_snapshot_keys_for_release(proj_key, release_id)
    if included is None:
        return set()
    all_keys = {iss["key"] for iss in issues}
    return all_keys - included

from ui.helpers_formatting import render_ticket_table, user_initials  # noqa: F401

