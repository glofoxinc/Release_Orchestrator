"""Unified startup session restore — one prompt for Platform + Deployer state."""

from __future__ import annotations

from typing import Any

import streamlit as st

import deploy_draft
import release_session as rs
from recovery_contract import platform_recovery_snapshot
from session_persist import draft_has_restorable_content


def _restore_summary_lines(draft: dict[str, Any]) -> list[str]:
    """Human-readable list of what the saved draft contains."""
    snap = platform_recovery_snapshot(
        {**draft, **(draft.get("release_session") or {})},
    )
    labels = {
        "snapshot": "Ticket Review lock",
        "release_notes": "Release Notes draft / DOCX",
        "sharepoint": "SharePoint link",
        "service_ticket": "SHIPIT draft or created ticket",
        "slack": "Slack announce state",
        "teams": "Teams meeting IDs",
        "deploy": "Deployer progress",
    }
    lines: list[str] = []
    for domain, label in labels.items():
        if snap.domains.get(domain):
            lines.append(label)
    if draft.get("wiz_release"):
        name = (draft.get("wiz_release") or {}).get("name", "")
        if name and "Deployer progress" not in lines:
            lines.append(f"Deployer release ({name})")
    session = draft.get("release_session") or {}
    stk_step = session.get("stk_step")
    if isinstance(stk_step, int) and stk_step >= 3:
        lines.append(f"SHIPIT wizard (step {stk_step} of 6)")
    return lines or ["Saved workflow progress"]


def _heal_restored_release_notes_session() -> None:
    """Rebuild RN draft fields after restore so Step 4 is not blocked."""
    try:
        from release_platform.ui.helpers import heal_session_after_restore

        heal_session_after_restore()
    except Exception:  # noqa: BLE001 — restore must never crash startup
        import logging

        logging.getLogger(__name__).debug(
            "Post-restore release notes heal skipped",
            exc_info=True,
        )


def render_startup_restore_prompt() -> bool:
    """Show unified restore dialog. Returns True if the app should stop (awaiting choice)."""
    if st.session_state.get("_release_session_prompt_done"):
        return False

    saved, restore_warning = deploy_draft.load_deploy_draft_with_reason()

    if not saved or not draft_has_restorable_content(saved):
        st.session_state["_release_session_prompt_done"] = True
        if restore_warning:
            st.error(
                "**Previous session not restored.** "
                + str(restore_warning)
                + " Fix the draft file or start a new release."
            )
        return False

    saved_at = saved.get("saved_at", "recently")
    items = _restore_summary_lines(saved)
    bullet = "\n".join(f"- {line}" for line in items)

    st.info(
        f"**Saved release progress found** (saved {saved_at}).\n\n"
        f"This will restore:\n{bullet}\n\n"
        "**Not restored:** ticket checkbox widget state (lists refetch from Jira). "
        "Quick-start mode flags are restored when saved."
    )
    if restore_warning:
        st.warning(
            "**Note after restore:** " + restore_warning
        )

    yes, no, _ = st.columns([1, 1, 3])
    with yes:
        if st.button("Restore session", type="primary", key="_restore_release_session"):
            rs.apply_release_session(st.session_state, saved)
            st.session_state["_release_session_prompt_done"] = True
            st.session_state["wiz_draft_prompt_done"] = True
            st.session_state["_session_restored_at"] = saved_at
            if restore_warning:
                st.session_state["_draft_scope_warning"] = restore_warning
            if saved.get("_scope_restore_blocked"):
                st.session_state["_scope_restore_blocked"] = True
                st.session_state["_scope_restore_changed"] = saved.get(
                    "_scope_restore_changed", []
                )
            _heal_restored_release_notes_session()
            from session_persist import persist_session

            persist_session(dict(st.session_state))
            st.rerun()
    with no:
        if st.button("Start fresh", key="_discard_release_session"):
            rs.clear_release_session()
            st.session_state["_release_session_prompt_done"] = True
            st.session_state["wiz_draft_prompt_done"] = True
            st.rerun()
    return True
