"""Release workflow — prerequisites, step guidance, and app gating."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st

import release_critical as rc
from release_platform.ui.helpers import esc, get_shared_release_summary, get_snapshot, navigate_to_app, workflow_blocked_by_scope


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    number: int
    label: str
    short: str


WORKFLOW_STEPS: tuple[WorkflowStep, ...] = (
    WorkflowStep("ticket_review", 1, "Ticket Review", "Lock ticket list"),
    WorkflowStep("release_notes", 2, "Release Notes", "Generate .docx"),
    WorkflowStep("service_ticket", 3, "Service Ticket", "Create SHIPIT"),
    WorkflowStep("release_deployer", 4, "Release Deployer", "Post-deploy"),
)


@dataclass
class PrerequisiteResult:
    ok: bool
    missing: list[str]
    fixes: list[tuple[str, str]]  # (app_id, button label)


def _has_snapshot() -> bool:
    snap = get_snapshot()
    return bool(snap and snap.get("ticket_keys"))


def _has_release_doc() -> bool:
    return bool(st.session_state.get("shared_docx_generated"))


def _has_sharepoint_link() -> bool:
    url = (st.session_state.get("shared_sharepoint_url") or "").strip()
    return url.startswith("http://") or url.startswith("https://")


def _has_service_ticket() -> bool:
    return bool(st.session_state.get("stk_created_key"))


def _dedupe_fixes(fixes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Keep one fix button per target app (first label wins)."""
    seen: dict[str, str] = {}
    for app, label in fixes:
        if app not in seen:
            seen[app] = label
    return list(seen.items())


def is_service_ticket_standalone() -> bool:
    """True when the user chose to create a SHIPIT ticket without the full release workflow."""
    return bool(st.session_state.get("shared_stk_standalone_mode"))


def enable_service_ticket_standalone() -> None:
    st.session_state["shared_stk_standalone_mode"] = True
    _persist_standalone_flags()


def disable_service_ticket_standalone() -> None:
    st.session_state.pop("shared_stk_standalone_mode", None)
    _persist_standalone_flags()


def is_deployer_standalone() -> bool:
    """True when the user posts deployment comments without the full release workflow."""
    return bool(st.session_state.get("shared_deployer_standalone_mode"))


def enable_deployer_standalone() -> None:
    st.session_state["shared_deployer_standalone_mode"] = True
    _persist_standalone_flags()


def disable_deployer_standalone() -> None:
    st.session_state.pop("shared_deployer_standalone_mode", None)
    _persist_standalone_flags()


def is_release_notes_standalone() -> bool:
    """True when generating release notes without Ticket Review lock."""
    return bool(st.session_state.get("shared_rn_standalone_mode"))


def enable_release_notes_standalone() -> None:
    st.session_state["shared_rn_standalone_mode"] = True
    _persist_standalone_flags()


def disable_release_notes_standalone() -> None:
    st.session_state.pop("shared_rn_standalone_mode", None)
    _persist_standalone_flags()


def _persist_standalone_flags() -> None:
    try:
        from session_persist import persist_session

        persist_session(dict(st.session_state))
    except Exception:  # noqa: BLE001
        pass


def _workflow_flags() -> rc.WorkflowFlags:
    return rc.WorkflowFlags(
        service_ticket_standalone=is_service_ticket_standalone(),
        release_notes_standalone=is_release_notes_standalone(),
        deployer_standalone=is_deployer_standalone(),
    )


def batch_app_prerequisites(app_ids: tuple[str, ...]) -> dict[str, PrerequisiteResult]:
    """Compute prerequisite results once per home render (avoids repeated session copies)."""
    if not app_ids:
        return {}
    blocked, blocking = workflow_blocked_by_scope()
    scope_blocking = list(blocking) if blocked else None
    flags = _workflow_flags()
    state = dict(st.session_state)
    out: dict[str, PrerequisiteResult] = {}
    for app_id in app_ids:
        result = rc.check_app_prerequisites(
            app_id,
            state,
            flags=flags,
            scope_blocking=scope_blocking,
        )
        out[app_id] = PrerequisiteResult(result.ok, result.missing, result.fixes)
    return out


def check_app_prerequisites(app_id: str) -> PrerequisiteResult:
    """Return whether the user may open ``app_id`` in the release workflow."""
    return batch_app_prerequisites((app_id,)).get(
        app_id,
        PrerequisiteResult(True, [], []),
    )


def navigate_step(step_session_key: str, step: int, *, persist: bool = True) -> None:
    """Shared step navigation — optional persist then rerun."""
    if persist:
        try:
            from session_persist import persist_session

            persist_session(dict(st.session_state))
        except Exception:  # noqa: BLE001
            pass
    st.session_state[step_session_key] = step
    st.rerun()


def get_workflow_progress() -> dict[str, bool]:
    """Checkpoint flags for home page and sidebar."""
    progress = rc.workflow_checkpoints(dict(st.session_state))
    if get_shared_release_summary():
        progress["releases"] = True
    return progress


def render_workflow_progress_bar(*, compact: bool = False) -> None:
    """Horizontal checklist of workflow checkpoints."""
    progress = get_workflow_progress()
    items = [
        ("releases", "Releases"),
        ("ticket_review", "Review locked"),
        ("release_notes", "Doc generated"),
        ("sharepoint", "SharePoint link"),
        ("service_ticket", "SHIPIT created"),
        ("deployer", "Deployed"),
    ]
    if compact:
        parts = []
        for key, label in items:
            mark = "\u2713" if progress.get(key) else "\u25cb"
            parts.append(f"{mark} {label}")
        st.caption(" **|** ".join(parts))
        return

    cols = st.columns(len(items))
    for col, (key, label) in zip(cols, items):
        done = progress.get(key, False)
        icon = "\u2705" if done else "\u2b55"
        col.markdown(f"{icon} **{label}**")


def render_workflow_status_strip() -> None:
    """Compact checkpoint row shown at the top of each workflow app."""
    render_workflow_progress_bar(compact=True)


def render_app_prerequisite_gate(app_id: str) -> bool:
    """Block app UI when prerequisites fail. Returns True if OK to continue."""
    result = check_app_prerequisites(app_id)
    if result.ok:
        return True

    step = next((s for s in WORKFLOW_STEPS if s.id == app_id), None)
    title = step.label if step else app_id
    st.markdown(f"## {title}")

    missing_snapshot = any("Ticket Review lock-in" in m for m in result.missing)
    if missing_snapshot:
        st.error(
            "**Ticket Review lock-in is required before this step.** "
            "In Ticket Review Step 2, select your tickets and click "
            "**Generate Review List →** to save the approved list."
        )
        from release_platform.ui.helpers import collect_cached_ticket_review_issues, lock_pending_ticket_review

        pending = collect_cached_ticket_review_issues()
        selected = st.session_state.get("tr_selected_keys")
        if pending:
            count = len(selected) if selected else len(pending)
            st.info(
                f"You already loaded **{count} ticket(s)** in Ticket Review this session. "
                "You can lock them here without starting over."
            )
            if st.button(
                f"Lock {count} selected ticket(s) now",
                type="primary",
                key=f"wf_gate_lock_{app_id}",
            ):
                outcome = lock_pending_ticket_review()
                if outcome.get("ok"):
                    st.success(str(outcome.get("message", "Locked.")))
                    st.rerun()
                else:
                    st.warning(str(outcome.get("message", "Could not lock tickets.")))
    else:
        st.error(
            "**This step is not available yet.** Complete the prior workflow steps first. "
            "Skipping steps can leave Jira tickets incomplete or incorrect."
        )

    st.markdown("**Still needed:**")
    for item in result.missing:
        st.markdown(f"- {esc(item)}")

    st.markdown("")
    st.markdown("**Recommended order:**")
    for ws in WORKFLOW_STEPS:
        st.markdown(f"{ws.number}. **{ws.label}** — {ws.short}")

    st.markdown("---")
    if app_id == "service_ticket":
        st.markdown(
            "**Or skip the full workflow:** create a Service Ticket directly by picking "
            "releases in Jira and pasting your SharePoint link manually."
        )
        if st.button(
            "Start Service Ticket independently \u2192",
            type="primary",
            key=f"wf_gate_{app_id}_standalone",
        ):
            enable_service_ticket_standalone()
            st.rerun()
        st.markdown("")
    if app_id == "release_deployer":
        st.markdown(
            "**Or use Quick start:** post deployment comments and transition tickets to Done "
            "without Ticket Review, Release Notes, or Service Ticket. You can still exclude "
            "individual tickets that failed in production on the Review step."
        )
        if st.button(
            "Quick start Release Deployer \u2192",
            type="primary",
            key=f"wf_gate_{app_id}_standalone",
        ):
            enable_deployer_standalone()
            st.rerun()
        st.markdown("")
    if app_id == "release_notes" and missing_snapshot:
        st.markdown(
            "**Or use Quick start:** pick releases and tickets directly in Release Notes Step 2 "
            "without locking Ticket Review first."
        )
        if st.button(
            "Quick start Release Notes \u2192",
            type="primary",
            key=f"wf_gate_{app_id}_standalone",
        ):
            enable_release_notes_standalone()
            st.rerun()
        st.markdown("")
    for idx, (fix_app, label) in enumerate(result.fixes):
        if st.button(
            f"{label} \u2192",
            type="primary",
            key=f"wf_gate_{app_id}_{fix_app}_{idx}",
        ):
            navigate_to_app(fix_app)
    if st.button("\U0001f3e0 Back to Home", key=f"wf_gate_home_{app_id}"):
        st.session_state.pop("active_app", None)
        st.rerun()
    return False


def render_step_banner(
    app_id: str,
    step: int,
    *,
    total_steps: int | None = None,
) -> None:
    """Context banner: what this step is for and what happens next."""
    if app_id == "release_deployer" and is_deployer_standalone():
        guide = _QUICK_DEPLOYER_GUIDES.get(step)
    elif app_id == "release_notes" and is_release_notes_standalone():
        guide = _QUICK_RN_GUIDES.get(step) or _STEP_GUIDES.get((app_id, step))
    elif app_id == "service_ticket" and is_service_ticket_standalone():
        guide = _QUICK_STK_GUIDES.get(step) or _STEP_GUIDES.get((app_id, step))
    else:
        guide = _STEP_GUIDES.get((app_id, step))
    if not guide:
        return
    total = total_steps or guide.get("total", "?")
    st.markdown(
        f'<div class="jt-banner jt-banner--info" style="margin-bottom:12px">'
        f'<div style="font-weight:700;margin-bottom:4px">'
        f'Step {step} of {total}: {esc(guide["title"])}</div>'
        f'<div style="font-size:.88rem;opacity:.9">{esc(guide["about"])}</div>'
        f'<div style="font-size:.85rem;margin-top:6px;opacity:.85">'
        f'<strong>When you click \u201c{esc(guide["button"])}\u201d:</strong> {esc(guide["next"])}'
        f"</div></div>",
        unsafe_allow_html=True,
    )


def render_action_hint(text: str) -> None:
    """Small caption under primary navigation buttons."""
    st.caption(text)


def mark_release_doc_generated(filename: str) -> None:
    st.session_state["shared_docx_filename"] = filename
    st.session_state["shared_docx_generated"] = True
    from session_persist import persist_session

    persist_session(dict(st.session_state))


def save_sharepoint_url(url: str, *, source: str = "shared") -> None:
    cleaned = (url or "").strip()
    st.session_state["shared_sharepoint_url"] = cleaned
    if cleaned or source == "stk":
        st.session_state["stk_sharepoint"] = cleaned
    from session_persist import persist_session

    persist_session(dict(st.session_state))


def validate_sharepoint_url(url: str, *, require_link_shape: bool = False) -> bool:
    """Validate SharePoint host + optional document link shape."""
    from sharepoint_url import validate_sharepoint_url as _validate

    return _validate(url, require_link_shape=require_link_shape)


def service_ticket_create_blockers(ss: dict) -> list[str]:
    """Hard blockers before irreversible SHIPIT creation."""
    flags = rc.WorkflowFlags(
        service_ticket_standalone=is_service_ticket_standalone(),
    )
    state = dict(ss)
    if not flags.service_ticket_standalone:
        state.setdefault("shared_docx_generated", st.session_state.get("shared_docx_generated"))
        state.setdefault("shared_snapshot", st.session_state.get("shared_snapshot"))
    return rc.service_ticket_create_blockers(state, flags=flags)


_STEP_GUIDES: dict[tuple[str, int], dict[str, Any]] = {
    ("ticket_review", 1): {
        "title": "Select tickets",
        "about": "Choose fix version(s) or filter by Jira status per project (PIC / AN).",
        "next": "Matching tickets load next — select which ones belong in this release.",
        "button": "Continue \u2192",
        "total": 3,
    },
    ("ticket_review", 2): {
        "title": "Review tickets",
        "about": "Tick the tickets that are approved for this release.",
        "next": "Your selection is saved as the locked ticket list used by all later steps.",
        "button": "Generate Review List \u2192",
        "total": 3,
    },
    ("ticket_review", 3): {
        "title": "Format & copy",
        "about": "Copy the review list for Teams/Slack. The lock-in is already saved.",
        "next": "Open Release Notes to build the Word document from the same ticket list.",
        "button": "Release Notes \u2192",
        "total": 3,
    },
    ("release_notes", 1): {
        "title": "Select tickets",
        "about": "Choose fix version(s) or Jira statuses (PIC / AN).",
        "next": "Matching tickets load on the next step for the Word document.",
        "button": "Continue \u2192",
        "total": 4,
    },
    ("release_notes", 2): {
        "title": "Choose tickets",
        "about": "Confirm which locked tickets appear in the release notes.",
        "next": "Editable summary and change table content is prepared on the next step.",
        "button": "Edit Content \u2192",
        "total": 4,
    },
    ("release_notes", 3): {
        "title": "Edit content",
        "about": "Review version, date, summaries, and change rows.",
        "next": "Preview the document and download the .docx file.",
        "button": "Preview & Generate \u2192",
        "total": 4,
    },
    ("release_notes", 4): {
        "title": "Generate & publish link",
        "about": "Download the .docx, upload it to SharePoint, then paste the link.",
        "next": "Service Ticket creation uses that link in the SHIPIT description.",
        "button": "Service Ticket \u2192",
        "total": 4,
    },
    ("service_ticket", 1): {
        "title": "Select tickets",
        "about": "Choose fix version(s) or Jira statuses, or use the locked Ticket Review list.",
        "next": "Tickets load for the SHIPIT description and deployment plans.",
        "button": "Continue \u2192",
        "total": 6,
    },
    ("service_ticket", 2): {
        "title": "Ticket details",
        "about": "Set summary, schedule, and confirm the SharePoint link to release notes.",
        "next": "The ADF description table is built from your locked tickets.",
        "button": "Build Description \u2192",
        "total": 6,
    },
    ("service_ticket", 3): {
        "title": "Description",
        "about": "Review the Jira description body (tables and SharePoint link).",
        "next": "Implementation, test, backout, and impact plans are generated next.",
        "button": "Edit Plans \u2192",
        "total": 6,
    },
    ("service_ticket", 4): {
        "title": "Deployment plans",
        "about": "Edit auto-generated plans before preview.",
        "next": "Coverage validation runs before the final create step.",
        "button": "Review & Create \u2192",
        "total": 6,
    },
    ("service_ticket", 5): {
        "title": "Preview",
        "about": "Validate consolidation, approvers, and coverage.",
        "next": "Final review — then one click creates the real SHIPIT ticket in Jira (cannot undo here).",
        "button": "Final Review \u2192",
        "total": 6,
    },
    ("service_ticket", 6): {
        "title": "Create in Jira",
        "about": "Last chance to verify everything. Creating the ticket is permanent.",
        "next": "After success, open Release Deployer to post deployment comments.",
        "button": "Create SHIPIT in Jira",
        "total": 6,
    },
    ("release_deployer", 1): {
        "title": "Select release",
        "about": "Choose the fix version you deployed under the SHIPIT change ticket.",
        "next": "Tickets from the locked list load for deployment comments.",
        "button": "Next \u2192",
        "total": 6,
    },
    ("release_deployer", 2): {
        "title": "Select tickets",
        "about": "Review tickets on the fix version before post-deploy updates.",
        "next": "Optionally remove the fix version from tickets that should not ship at all.",
        "button": "Next \u2192",
        "total": 6,
    },
    ("release_deployer", 3): {
        "title": "Exclude tickets",
        "about": "Remove the fix version from tickets that should not ship with this release.",
        "next": "Enter deployment ID, date, and time for each client.",
        "button": "Next \u2192",
        "total": 6,
    },
    ("release_deployer", 4): {
        "title": "Deployment info",
        "about": "Fill deployment comments per client or project.",
        "next": "Review the full deploy plan before executing.",
        "button": "Next \u2192",
        "total": 6,
    },
    ("release_deployer", 5): {
        "title": "Review deploy plan",
        "about": "Choose which tickets get deployment comments and Done transitions.",
        "next": "Uncheck tickets that failed in production — the rest update as usual.",
        "button": "Deploy Now \u2192",
        "total": 6,
    },
    ("release_deployer", 6): {
        "title": "Execute deployment",
        "about": "Posts deployment comments and transitions tickets. This updates Jira.",
        "next": "Results are saved to deploy history; you can undo recent changes if needed.",
        "button": "Deploy",
        "total": 6,
    },
}

_QUICK_RN_GUIDES: dict[int, dict[str, Any]] = {
    1: {
        "title": "Select tickets (quick start)",
        "about": (
            "Pick fix version(s) or board statuses, then optional Jira Team filter "
            "(PIC / AN) — no Ticket Review lock required."
        ),
        "next": "Tickets load on Step 2. PIC defaults to Review, AN to Passed QA.",
        "button": "Continue \u2192",
        "total": 4,
    },
    2: {
        "title": "Choose tickets",
        "about": "All matching tickets are pre-selected. Uncheck any you want to omit.",
        "next": "Step 3 edits summaries and the change table; Step 4 previews and downloads .docx.",
        "button": "Next → Edit Content (Step 3 of 4)",
        "total": 4,
    },
    3: {
        "title": "Edit release notes content",
        "about": "Review metadata, summaries, deployment rows, and change table text.",
        "next": "Step 4 opens preview and .docx download.",
        "button": "Preview & Generate \u2192",
        "total": 4,
    },
    4: {
        "title": "Preview and generate",
        "about": "Preview in browser, download the Word file, then upload to SharePoint.",
        "next": "Optional: continue to SHIPIT or Deployer in the full workflow.",
        "button": "Generate DOCX",
        "total": 4,
    },
}

_QUICK_STK_GUIDES: dict[int, dict[str, Any]] = {
    1: {
        "title": "Select tickets (quick start)",
        "about": (
            "Pick fix version(s) or board statuses, optional Jira Team filter — "
            "create SHIPIT without Ticket Review."
        ),
        "next": "Tickets load from Jira; then enter schedule and paste your SharePoint link.",
        "button": "Continue \u2192",
        "total": 6,
    },
    2: {
        "title": "Ticket details",
        "about": "Set summary, schedule, and paste the SharePoint link to release notes.",
        "next": "The SHIPIT description is built from your ticket list.",
        "button": "Build Description \u2192",
        "total": 6,
    },
}

_QUICK_DEPLOYER_GUIDES: dict[int, dict[str, Any]] = {
    1: {
        "title": "Select release",
        "about": "Pick the fix version you deployed to production.",
        "next": "Tickets on that version load — you choose which to update.",
        "button": "Continue \u2192",
        "total": 5,
    },
    2: {
        "title": "Select tickets",
        "about": "All tickets on the fix version are checked by default.",
        "next": "Uncheck any that failed in production, then enter deployment info.",
        "button": "Next \u2192",
        "total": 5,
    },
    3: {
        "title": "Deployment info",
        "about": "Paste or enter deployment ID, date, and time.",
        "next": "Review the plan before posting comments to Jira.",
        "button": "Next \u2192",
        "total": 5,
    },
    4: {
        "title": "Review",
        "about": "Confirm deployment details and selected tickets.",
        "next": "Posts comments and transitions checked tickets to Done.",
        "button": "Deploy Now \u2192",
        "total": 5,
    },
    5: {
        "title": "Deploy",
        "about": "Posting deployment comments and updating ticket status in Jira.",
        "next": "Results appear below; you can undo recent changes if needed.",
        "button": "Deploy",
        "total": 5,
    },
}
