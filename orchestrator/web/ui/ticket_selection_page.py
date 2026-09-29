"""Ticket checkbox pages — stay on step, no auto-back, preserve manual selection."""

from __future__ import annotations

import hashlib

import streamlit as st


def _norm_prefix(prefix: str) -> str:
    return prefix if prefix.endswith("_") else f"{prefix}_"


def step2_loaded_key(prefix: str) -> str:
    return f"{_norm_prefix(prefix)}step2_loaded"


def issues_fingerprint(issues: list[dict]) -> str:
    keys = sorted(str(iss.get("key") or "") for iss in issues)
    keys = [k for k in keys if k]
    if not keys:
        return "empty"
    return hashlib.sha256("|".join(keys).encode("utf-8")).hexdigest()[:16]


def mark_step2_loaded(prefix: str) -> None:
    st.session_state[step2_loaded_key(prefix)] = True


def clear_step2_loaded(prefix: str) -> None:
    st.session_state.pop(step2_loaded_key(prefix), None)


def is_step2_loaded(prefix: str) -> bool:
    return bool(st.session_state.get(step2_loaded_key(prefix)))


def should_auto_back_to_step1(
    prefix: str,
    *,
    has_source_selection: bool,
    has_cached_tickets: bool = False,
    has_snapshot_issues: bool = False,
) -> bool:
    """True only when step 2 was never entered and there is nothing to show."""
    if is_step2_loaded(prefix):
        return False
    if has_cached_tickets:
        return False
    if has_snapshot_issues:
        return False
    return not has_source_selection


def render_stay_on_page_hint(*, action_label: str = "Continue") -> None:
    st.caption(
        f"Check or uncheck tickets freely — you **stay on this page** until you click "
        f"**{action_label}** or **Change filters**."
    )


def render_empty_selection_hint(*, mode_label: str = "tickets") -> None:
    st.info(
        f"No {mode_label} selected. Use **Select All** or check individually — "
        "you can change your selection anytime before continuing."
    )
