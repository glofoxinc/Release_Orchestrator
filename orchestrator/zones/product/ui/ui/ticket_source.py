"""Shared ticket loading — fix version or Jira status, used by Ticket Review / RN / SHIPIT."""

from __future__ import annotations

import hashlib
from typing import Callable

import streamlit as st

import config
import jira_client
from release_platform.ui.helpers import esc, normalize_version_id, scope_fingerprint_for_project

MODE_FIX_VERSION = "fix_version"
MODE_STATUS = "status"


def _norm_prefix(prefix: str) -> str:
    return prefix if prefix.endswith("_") else f"{prefix}_"


def mode_session_key(prefix: str) -> str:
    return f"{_norm_prefix(prefix)}selection_mode"


def status_session_key(prefix: str, project_key: str) -> str:
    return f"{_norm_prefix(prefix)}statuses_{project_key}"


def locked_source_key(prefix: str) -> str:
    return f"{_norm_prefix(prefix)}locked_ticket_source"


def source_fp_session_key(prefix: str) -> str:
    p = _norm_prefix(prefix).rstrip("_")
    return f"{p}_source_fp"


def status_options_cache_key(project_key: str) -> str:
    return f"_status_options_{project_key}"


def get_selection_mode(prefix: str) -> str:
    mode = st.session_state.get(mode_session_key(prefix), MODE_FIX_VERSION)
    return mode if mode in {MODE_FIX_VERSION, MODE_STATUS} else MODE_FIX_VERSION


def step1_continue_label(prefix: str) -> str:
    """Mode-aware Step 1 primary button label."""
    if get_selection_mode(prefix) == MODE_FIX_VERSION:
        return "Confirm fix version(s) \u2192"
    return "Confirm statuses \u2192"


def get_locked_ticket_source(prefix: str) -> dict | None:
    raw = st.session_state.get(locked_source_key(prefix))
    return raw if isinstance(raw, dict) else None


def rebuild_locked_from_fingerprint(prefix: str, fingerprint: str) -> dict | None:
    """Rebuild a locked source blob from a saved selection fingerprint (session recovery)."""
    if not fingerprint:
        return None
    parts = fingerprint.split("|")
    mode = parts[0]
    if mode not in {MODE_FIX_VERSION, MODE_STATUS}:
        return None

    locked: dict = {
        "mode": mode,
        "summary": "",
        "statuses": {},
        "releases": {},
    }
    summary_parts: list[str] = []
    p = _norm_prefix(prefix)
    valid_pks = {proj["key"] for proj in config.PROJECTS}

    for part in parts[1:]:
        if part.startswith("teams:"):
            break
        if ":" not in part:
            continue
        pk, val = part.split(":", 1)
        if pk not in valid_pks:
            continue
        if mode == MODE_STATUS and val:
            statuses = [s.strip() for s in val.split(",") if s.strip()]
            if statuses:
                locked["statuses"][pk] = statuses
                summary_parts.append(f"{pk}: {', '.join(statuses)}")
        elif mode == MODE_FIX_VERSION and val:
            if "#" in val:
                rid, name = val.split("#", 1)
            else:
                rid, name = val, ""
            locked["releases"][pk] = {"id": rid, "name": name}
            summary_parts.append(f"{pk}: {esc(name)}" if name else f"{pk}: {rid}")

    locked["summary"] = " + ".join(summary_parts)
    return locked if summary_parts or mode == MODE_STATUS else None


def ensure_locked_ticket_source(prefix: str) -> dict | None:
    """Return locked ticket source, rebuilding from fingerprint when upgrading old sessions."""
    locked = get_locked_ticket_source(prefix)
    if locked:
        return locked
    fp = st.session_state.get(source_fp_session_key(prefix))
    if not fp:
        return None
    rebuilt = rebuild_locked_from_fingerprint(prefix, str(fp))
    if rebuilt:
        st.session_state[locked_source_key(prefix)] = rebuilt
    return rebuilt


def lock_ticket_source(prefix: str) -> dict:
    """Snapshot mode, statuses, and releases when the user continues to ticket selection."""
    from release_platform.ui.helpers import get_snapshot

    p = _norm_prefix(prefix)
    mode = get_selection_mode(prefix)
    snap = get_snapshot()
    if mode == MODE_STATUS and not (snap and snap.get("ticket_keys")):
        if not has_status_selection(prefix=prefix):
            raise ValueError(
                "Select at least one Jira status on PIC or AN before continuing."
            )
    locked: dict = {
        "mode": mode,
        "summary": selection_summary(prefix=prefix),
        "statuses": {
            proj["key"]: list(get_selected_statuses(prefix, proj["key"]))
            for proj in config.PROJECTS
        },
        "releases": {},
    }
    for proj in config.PROJECTS:
        pk = proj["key"]
        rel = st.session_state.get(f"{p}release_{pk}", {})
        if rel:
            locked["releases"][pk] = dict(rel)

    st.session_state[locked_source_key(prefix)] = locked
    return locked


def _step_number(prefix: str) -> int:
    """Current wizard step for prefix (rn/stk/tr)."""
    p = _norm_prefix(prefix).rstrip("_")
    raw = st.session_state.get(f"{p}_step", 1)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def get_effective_statuses(prefix: str, project_key: str) -> list[str]:
    """Statuses for fetch/fingerprint — prefers locked snapshot over live widgets."""
    locked = ensure_locked_ticket_source(prefix)
    if locked and get_effective_selection_mode(prefix) == MODE_STATUS:
        raw = (locked.get("statuses") or {}).get(project_key) or []
        cleaned = [str(s).strip() for s in raw if str(s).strip()]
        if cleaned:
            return cleaned
    return get_selected_statuses(prefix, project_key)


def get_effective_release(prefix: str, project_key: str) -> dict:
    """Release object for fetch/fingerprint — prefers locked snapshot."""
    locked = ensure_locked_ticket_source(prefix)
    p = _norm_prefix(prefix)
    if locked and get_effective_selection_mode(prefix) == MODE_FIX_VERSION:
        rel = (locked.get("releases") or {}).get(project_key)
        if rel:
            return dict(rel)
    rel = st.session_state.get(f"{p}release_{project_key}", {})
    return dict(rel) if rel else {}


def clear_locked_ticket_source(prefix: str) -> None:
    st.session_state.pop(locked_source_key(prefix), None)


def apply_locked_ticket_source(prefix: str) -> dict | None:
    """Re-apply locked status/releases on downstream steps (after Step 1 widgets).

    Does not write ``*_selection_mode`` or status multiselect keys while Step 1 is
    still active — Streamlit forbids mutating widget-bound session keys after render.
    """
    locked = ensure_locked_ticket_source(prefix)
    if not locked:
        return None

    if _step_number(prefix) <= 1:
        return locked

    for pk, statuses in (locked.get("statuses") or {}).items():
        cleaned = [str(s).strip() for s in statuses if str(s).strip()]
        if cleaned:
            st.session_state[status_session_key(prefix, str(pk))] = cleaned

    p = _norm_prefix(prefix)
    for pk, rel in (locked.get("releases") or {}).items():
        if rel:
            st.session_state[f"{p}release_{pk}"] = dict(rel)

    return locked


def get_effective_selection_mode(prefix: str) -> str:
    locked = ensure_locked_ticket_source(prefix)
    if locked and locked.get("mode") in {MODE_FIX_VERSION, MODE_STATUS}:
        return locked["mode"]
    return get_selection_mode(prefix)


def effective_selection_summary(*, prefix: str) -> str:
    locked = ensure_locked_ticket_source(prefix)
    if locked and locked.get("summary"):
        return str(locked["summary"])
    return selection_summary(prefix=prefix)


def get_selected_statuses(prefix: str, project_key: str) -> list[str]:
    raw = st.session_state.get(status_session_key(prefix, project_key)) or []
    if not isinstance(raw, list):
        return []
    return [str(s).strip() for s in raw if str(s).strip()]


def has_fix_version_selection(*, prefix: str) -> bool:
    p = _norm_prefix(prefix)
    return any(
        bool(st.session_state.get(f"{p}release_{proj['key']}", {}))
        for proj in config.PROJECTS
    )


def has_status_selection(*, prefix: str) -> bool:
    return any(get_selected_statuses(prefix, proj["key"]) for proj in config.PROJECTS)


def has_step1_selection(*, prefix: str) -> bool:
    locked = ensure_locked_ticket_source(prefix)
    if locked:
        mode = locked.get("mode")
        if mode == MODE_STATUS:
            return any(
                locked.get("statuses", {}).get(proj["key"])
                for proj in config.PROJECTS
            )
        return any(locked.get("releases", {}).get(proj["key"]) for proj in config.PROJECTS)
    if get_selection_mode(prefix) == MODE_STATUS:
        return has_status_selection(prefix=prefix)
    return has_fix_version_selection(prefix=prefix)


def load_project_status_options(project_key: str) -> list[str]:
    cache_key = status_options_cache_key(project_key)
    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = jira_client.get_project_status_names(project_key)
        except Exception:  # noqa: BLE001
            st.session_state[cache_key] = []
    return list(st.session_state[cache_key] or [])


def _default_status_targets(prefix: str, project_key: str) -> list[str]:
    """Ticket Review uses review-ready statuses; Release Notes uses release-ready only."""
    p = _norm_prefix(prefix).rstrip("_").lower()
    if p == "rn":
        return list(config.release_notes_default_statuses(project_key))
    return list(config.ticket_review_default_checked_statuses(project_key))


def apply_default_status_selections(prefix: str, *, force: bool = False) -> None:
    """Pre-fill status multiselect (TR: review-ready · RN: release-ready · STK: review-ready)."""
    for proj in config.PROJECTS:
        pk = proj["key"]
        sel_key = status_session_key(prefix, pk)
        if get_selected_statuses(prefix, pk) and not force:
            continue
        options = load_project_status_options(pk)
        if not options:
            continue
        options_map = {name.casefold(): name for name in options}
        picked: list[str] = []
        for target in _default_status_targets(prefix, pk):
            canonical = options_map.get(target.casefold())
            if canonical and canonical not in picked:
                picked.append(canonical)
        if picked:
            st.session_state[sel_key] = picked


def clear_fix_version_selection(*, prefix: str) -> None:
    from release_platform.ui.helpers import clear_shared_release

    for proj in config.PROJECTS:
        pk = proj["key"]
        clear_shared_release(prefix, pk)
        st.session_state.pop(f"{prefix}release_{pk}", None)


def clear_status_selection(*, prefix: str) -> None:
    p = _norm_prefix(prefix)
    for proj in config.PROJECTS:
        pk = proj["key"]
        st.session_state.pop(status_session_key(prefix, pk), None)
        for key in list(st.session_state.keys()):
            if key.startswith(f"_{p.rstrip('_')}_status_issues_{pk}_"):
                st.session_state.pop(key, None)


def on_mode_change(prefix: str) -> None:
    mode = get_selection_mode(prefix)
    if mode == MODE_FIX_VERSION:
        clear_status_selection(prefix=prefix)
    else:
        clear_fix_version_selection(prefix=prefix)
        apply_default_status_selections(prefix, force=True)


def status_issues_cache_key(
    prefix: str,
    project_key: str,
    statuses: tuple[str, ...],
) -> str:
    from release_platform.ui import jira_team_filter as jtf

    fp = scope_fingerprint_for_project(project_key) or "unscoped"
    team_suffix = jtf.team_filter_cache_suffix(prefix, project_key)
    digest = hashlib.sha256(
        "|".join(sorted(s.lower() for s in statuses)).encode("utf-8"),
    ).hexdigest()[:12]
    p = _norm_prefix(prefix).rstrip("_")
    return f"_{p}_status_issues_{project_key}_{digest}_{fp}_{team_suffix}"


def selection_summary(*, prefix: str) -> str:
    """Human-readable summary from live Step 1 session state."""
    mode = get_selection_mode(prefix)
    if mode == MODE_STATUS:
        parts: list[str] = []
        for proj in config.PROJECTS:
            pk = proj["key"]
            statuses = get_selected_statuses(prefix, pk)
            if statuses:
                parts.append(f"{pk}: {', '.join(statuses)}")
        return " + ".join(parts)
    parts = []
    p = _norm_prefix(prefix)
    for proj in config.PROJECTS:
        pk = proj["key"]
        rel = st.session_state.get(f"{p}release_{pk}", {})
        if rel:
            parts.append(f"{pk}: {esc(rel.get('name', ''))}")
    return " + ".join(parts)


def render_selection_mode_radio(prefix: str) -> None:
    key = mode_session_key(prefix)
    if key not in st.session_state:
        st.session_state[key] = MODE_FIX_VERSION
    prev = st.session_state.get(key, MODE_FIX_VERSION)
    st.radio(
        "Selection mode",
        options=[MODE_FIX_VERSION, MODE_STATUS],
        format_func=lambda m: "Fix version" if m == MODE_FIX_VERSION else "By status (board)",
        horizontal=True,
        key=key,
        help=(
            "**Fix version** — unreleased Jira versions. "
            "**By status** — workflow statuses (e.g. Review, Passed QA)."
        ),
    )
    if st.session_state[key] != prev:
        on_mode_change(prefix)
        st.rerun()


def render_status_picker(prefix: str) -> None:
    apply_default_status_selections(prefix, force=False)
    for proj in config.PROJECTS:
        pk = proj["key"]
        st.markdown(f"### {pk} board")
        options = load_project_status_options(pk)
        if not options:
            st.info(
                f"Could not load statuses for {pk}. Check Jira credentials and project access."
            )
            continue
        st.multiselect(
            f"{pk} statuses",
            options=options,
            key=status_session_key(prefix, pk),
            help="Tickets matching any selected status are loaded on the next step.",
        )
        selected = get_selected_statuses(prefix, pk)
        if selected:
            st.caption(f"Selected: {', '.join(selected)}")


def fetch_combined_issues(
    prefix: str,
    *,
    issues_cache_prefix: str,
    team_ids_for_project: Callable[[str], list[str] | None] | None = None,
    force: bool = False,
) -> list[dict]:
    """Fetch issues from fix versions or status filters across configured projects."""
    all_issues: list[dict] = []
    seen: set[str] = set()
    mode = get_effective_selection_mode(prefix)

    p = _norm_prefix(prefix)

    for proj in config.PROJECTS:
        pk = proj["key"]
        team_ids = team_ids_for_project(pk) if team_ids_for_project else None
        batch: list[dict] = []

        if mode == MODE_STATUS:
            statuses = get_effective_statuses(prefix, pk)
            if not statuses:
                continue
            cache_key = status_issues_cache_key(prefix, pk, tuple(sorted(statuses)))
            if force or cache_key not in st.session_state:
                try:
                    batch = jira_client.get_issues_for_statuses(
                        pk, statuses, jira_team_ids=team_ids,
                    )
                except Exception as exc:  # noqa: BLE001
                    st.session_state[f"_{p.rstrip('_')}_fetch_error_{pk}"] = str(exc)
                    batch = []
                st.session_state[cache_key] = batch
            else:
                batch = list(st.session_state.get(cache_key) or [])
        else:
            rel = get_effective_release(prefix, pk)
            if not rel:
                continue
            rid = normalize_version_id(rel["id"])
            from release_platform.ui.helpers import ticket_issues_cache_key

            cache_key = ticket_issues_cache_key(pk, rid, prefix=issues_cache_prefix)
            from release_platform.ui import jira_team_filter as jtf

            cache_key = f"{cache_key}_{jtf.team_filter_cache_suffix(prefix, pk)}"
            if force or cache_key not in st.session_state:
                try:
                    batch = jira_client.get_issues_for_version(
                        pk, rid, jira_team_ids=team_ids,
                    )
                except Exception as exc:  # noqa: BLE001
                    st.session_state[f"_{p.rstrip('_')}_fetch_error_{pk}"] = str(exc)
                    batch = []
                st.session_state[cache_key] = batch
            else:
                batch = list(st.session_state.get(cache_key) or [])

        for iss in batch:
            key = iss.get("key")
            if key and key not in seen:
                seen.add(key)
                all_issues.append(iss)

    return all_issues


def selection_fingerprint(prefix: str) -> str:
    """Stable fingerprint for current ticket source (mode, releases/statuses, teams)."""
    from release_platform.ui import jira_team_filter as jtf

    p = _norm_prefix(prefix)
    locked = ensure_locked_ticket_source(prefix)
    mode = get_effective_selection_mode(prefix)
    parts = [mode]
    if mode == MODE_STATUS:
        for proj in config.PROJECTS:
            pk = proj["key"]
            statuses = get_effective_statuses(prefix, pk)
            if statuses:
                parts.append(f"{pk}:{','.join(sorted(statuses))}")
    else:
        for proj in config.PROJECTS:
            pk = proj["key"]
            rel = get_effective_release(prefix, pk)
            rid = rel.get("id")
            name = str(rel.get("name") or "")
            rid_norm = normalize_version_id(rid) if rid is not None and rid != "" else ""
            parts.append(f"{pk}:{rid_norm}#{name}" if name else f"{pk}:{rid_norm}")
    parts.append(jtf.team_filter_fingerprint(prefix))
    return "|".join(parts)


def apply_snapshot_selection_context(prefix: str, snapshot: dict | None) -> None:
    """Restore selection mode + status filters from a Ticket Review snapshot."""
    if not snapshot:
        return
    if get_locked_ticket_source(prefix):
        return

    mode_key = mode_session_key(prefix)
    snap_mode = snapshot.get("selection_mode")
    if mode_key not in st.session_state and snap_mode in {MODE_FIX_VERSION, MODE_STATUS}:
        st.session_state[mode_key] = snap_mode

    status_filters = snapshot.get("status_filters") or {}
    if not isinstance(status_filters, dict):
        return
    for pk, statuses in status_filters.items():
        if not isinstance(statuses, list):
            continue
        sel_key = status_session_key(prefix, str(pk))
        if sel_key in st.session_state:
            continue
        cleaned = [str(s).strip() for s in statuses if str(s).strip()]
        if cleaned:
            st.session_state[sel_key] = cleaned
