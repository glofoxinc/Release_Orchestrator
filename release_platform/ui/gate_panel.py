"""Shared UI for pre-review and post-QA release gates."""

from __future__ import annotations

import streamlit as st

import release_gates
from slack_assignee_notify import gate_slack_status


def _version_from_prefix(prefix: str) -> str:
    parts: list[str] = []
    import config

    for proj in config.PROJECTS:
        rel = st.session_state.get(f"{prefix}release_{proj['key']}", {})
        if rel.get("name"):
            parts.append(str(rel["name"]))
    return " + ".join(parts) if parts else ""


def render_pre_review_panel(
    issues: list[dict],
    *,
    session_prefix: str = "tr_",
) -> tuple[list[dict], list[release_gates.GateTicket]]:
    """Filter review list and show held-back tickets + Slack notify controls."""
    if not release_gates.ticket_review_pre_review_enabled():
        st.session_state.pop(f"{session_prefix}pre_review_held", None)
        return issues, []

    result = release_gates.classify_pre_review(issues)
    held = result.blocked
    reviewable = result.ready
    st.session_state[f"{session_prefix}pre_review_held"] = [t.key for t in held]

    if held:
        st.warning(
            f"**{len(held)}** ticket(s) are not in a review-ready Jira status and are "
            f"hidden from this list. Allowed statuses: "
            + ", ".join(release_gates.pre_review_statuses())
        )
        with st.expander(f"Held back from review ({len(held)})", expanded=False):
            for ticket in held:
                st.markdown(
                    f"- **{ticket.key}** — {ticket.summary} · _{ticket.status}_ · "
                    f"{ticket.assignee_name}"
                )

        col_a, col_b = st.columns(2)
        with col_a:
            preview = st.button(
                "Preview Slack to assignees",
                key=f"{session_prefix}pre_review_preview",
                use_container_width=True,
            )
        with col_b:
            send = st.button(
                "Send Slack to assignees",
                key=f"{session_prefix}pre_review_send",
                type="primary",
                use_container_width=True,
            )
        version = _version_from_prefix("tr_")
        if preview or send:
            payload = release_gates.run_pre_review_gate(
                issues,
                version_name=version,
                notify=True,
                dry_run=not send,
            )
            slack = payload.get("slack") or {}
            if slack.get("status") == "dry_run":
                st.info(f"Dry-run: would notify {slack.get('recipient_count', 0)} assignee(s).")
                with st.expander("All assignee messages (bulk preview)", expanded=True):
                    for item in slack.get("previews") or []:
                        st.markdown(
                            f"**{item.get('assignee_name')}** — "
                            f"{', '.join(item.get('ticket_keys') or [])}"
                        )
                        st.text(item.get("message_preview") or "")
                        st.divider()
            elif slack.get("status") in {"ok", "partial"}:
                st.success(
                    f"Slack sent to {slack.get('ok_count', 0)}/{slack.get('recipient_count', 0)} assignee(s)."
                )
            elif slack.get("status") == "error":
                st.error(slack.get("error") or "Slack notify failed.")
            else:
                st.caption(str(slack))

        slack_status = gate_slack_status()
        if not slack_status.get("bot_token_configured"):
            st.caption("Set SLACK_BOT_TOKEN (with im:write + users:read.email) to DM assignees.")

    return reviewable, held


def apply_post_qa_exclusions(
    *,
    issues: list[dict],
    extracted: list[dict],
    selected_keys: set[str],
    session_prefix: str = "rn_",
) -> tuple[set[str], list[release_gates.GateTicket]]:
    """Run post-QA gate and return updated selection + blocked tickets."""
    result = release_gates.classify_post_qa(issues)
    blocked_keys = {t.key for t in result.blocked}
    new_selected = selected_keys - blocked_keys
    return new_selected, result.blocked


def render_post_qa_panel(
    issues: list[dict],
    *,
    extracted: list[dict],
    selected_keys: set[str],
    on_apply,
    session_prefix: str = "rn_",
) -> None:
    """Post-QA controls for Release Notes ticket step."""
    if not release_gates.post_qa_release_notes_enabled():
        return

    st.markdown("#### Post-QA gate")
    st.caption(
        "Tickets not in a QA-passed Jira status can be excluded from Release Notes "
        "and the release, with Slack reminders to assignees."
    )

    scope_issues = [iss for iss in issues if iss.get("key") in selected_keys] or issues
    classify = release_gates.classify_post_qa(scope_issues)
    if classify.blocked:
        st.warning(
            f"**{len(classify.blocked)}** selected ticket(s) are not in a QA-passed status "
            f"(expected: {', '.join(release_gates.qa_passed_statuses())})."
        )
        with st.expander(f"QA failures ({len(classify.blocked)})", expanded=False):
            for ticket in classify.blocked:
                st.markdown(
                    f"- **{ticket.key}** — _{ticket.status}_ · {ticket.assignee_name}"
                )
    else:
        st.success("All selected tickets pass the QA status gate.")

    slack_status = gate_slack_status()
    if not slack_status.get("bot_token_configured"):
        st.caption(
            "Set SLACK_BOT_TOKEN (scopes: im:write, users:read.email) to DM assignees on exclude."
        )

    preview = st.button(
        "Preview QA failures",
        key=f"{session_prefix}post_qa_preview",
        use_container_width=True,
    )
    apply_notify = st.button(
        "Exclude QA failures + notify assignees",
        key=f"{session_prefix}post_qa_apply",
        type="primary",
        use_container_width=True,
    )

    if not (preview or apply_notify):
        return

    version = _version_from_prefix(session_prefix)
    payload = release_gates.run_post_qa_gate(
        [iss for iss in issues if iss.get("key") in selected_keys] or issues,
        version_name=version,
        notify=apply_notify,
        dry_run=preview and not apply_notify,
    )
    blocked = payload.get("blocked") or []
    if not blocked:
        st.success("All tickets pass the QA status gate.")
        return

    st.warning(f"{len(blocked)} ticket(s) failed QA status check.")
    for row in blocked:
        st.markdown(f"- **{row['key']}** — _{row['status']}_ — {row['assignee_name']}")

    if apply_notify:
        blocked_objs = [
            release_gates.GateTicket(
                key=row["key"],
                summary=row.get("summary") or "",
                status=row.get("status") or "",
                assignee_name=row.get("assignee_name") or "",
                assignee_email=row.get("assignee_email") or "",
                project=row.get("project") or "",
                reason=row.get("reason") or "",
            )
            for row in blocked
        ]
        on_apply(blocked_objs, payload)
        slack = payload.get("slack") or {}
        if slack.get("status") in {"ok", "partial"}:
            st.success(
                f"Excluded from release and notified "
                f"{slack.get('ok_count', 0)}/{slack.get('recipient_count', 0)} assignee(s)."
            )
        elif slack.get("status") == "error":
            st.error(slack.get("error") or "Slack notify failed.")
    elif preview:
        slack = payload.get("slack") or {}
        if slack.get("previews"):
            st.info(f"Would notify {slack.get('recipient_count', 0)} assignee(s).")
            with st.expander("All assignee messages (bulk preview)", expanded=True):
                for item in slack.get("previews") or []:
                    st.markdown(
                        f"**{item.get('assignee_name')}** — "
                        f"{', '.join(item.get('ticket_keys') or [])}"
                    )
                    st.text(item.get("message_preview") or "")
                    st.divider()
