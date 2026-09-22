"""AI Ticket Creator — Streamlit page for natural-language ticket creation."""

from __future__ import annotations

import streamlit as st

import config
from ai_ticket_creator import create_ticket_from_nl, parse_ticket_from_nl


def render() -> None:
    st.markdown("## \U0001f916 AI Ticket Creator")
    st.markdown(
        "Describe what you need in plain English and the tool will parse it into "
        "a structured Jira ticket with auto-detected type, priority, and component."
    )

    st.markdown("")

    col_input, col_preview = st.columns([1, 1], gap="large")

    with col_input:
        st.markdown("#### Describe your ticket")

        project_keys = config.project_keys()
        if not project_keys:
            st.warning("No projects configured. Go to Settings to add projects.")
            return

        selected_project = st.selectbox(
            "Target Project",
            options=project_keys,
            key="aitc_project",
            help="The Jira project where the ticket will be created.",
        )

        nl_input = st.text_area(
            "Ticket Description (natural language)",
            height=200,
            placeholder=(
                "Example: There's a bug in the monthly revenue dashboard for Jetts — "
                "the YoY comparison chart is showing incorrect values for March 2026. "
                "This is impacting the client's monthly review meeting tomorrow. "
                "Priority: urgent."
            ),
            key="aitc_description",
        )

        parse_col, create_col = st.columns(2)
        with parse_col:
            parse_clicked = st.button(
                "\U0001f50d Parse & Preview",
                type="secondary",
                use_container_width=True,
                disabled=not nl_input.strip(),
            )
        with create_col:
            create_clicked = st.button(
                "\u2705 Create in Jira",
                type="primary",
                use_container_width=True,
                disabled=not nl_input.strip(),
            )

    if parse_clicked and nl_input.strip():
        parsed = parse_ticket_from_nl(nl_input, selected_project)
        st.session_state["aitc_parsed"] = parsed
        st.session_state.pop("aitc_created", None)

    if create_clicked and nl_input.strip():
        create_key = f"{selected_project}:{nl_input.strip()}"
        if st.session_state.get("aitc_last_create_key") == create_key:
            st.warning("This ticket was already created from the same description. Edit the text to create another.")
        else:
            with st.spinner("Creating ticket in Jira..."):
                try:
                    result = create_ticket_from_nl(nl_input, selected_project)
                    st.session_state["aitc_created"] = result
                    st.session_state["aitc_parsed"] = result.get("fields")
                    st.session_state["aitc_last_create_key"] = create_key
                except Exception as exc:
                    st.error(f"Failed to create ticket: {exc}")

    with col_preview:
        parsed = st.session_state.get("aitc_parsed")
        created = st.session_state.get("aitc_created")

        if created and created.get("key"):
            st.success(f"Ticket created: **{created['key']}**")
            if created.get("url"):
                st.markdown(f"[\U0001f517 Open in Jira]({created['url']})")
            jira_fields = created.get("jira_fields") or {}
            sent_parts = []
            if jira_fields.get("priority"):
                sent_parts.append(f"priority **{jira_fields['priority'].get('name', '')}**")
            if jira_fields.get("components"):
                names = ", ".join(c.get("name", "") for c in jira_fields["components"])
                if names:
                    sent_parts.append(f"component **{names}**")
            if jira_fields.get("labels"):
                sent_parts.append(f"labels `{', '.join(jira_fields['labels'])}`")
            if sent_parts:
                st.caption("Sent to Jira: " + " · ".join(sent_parts))
            st.markdown("")

        if parsed:
            st.markdown("#### Parsed Fields")

            st.markdown(
                f'<div style="border:1px solid rgba(150,150,150,.15);border-radius:12px;'
                f'padding:16px 20px;background:rgba(150,150,150,.03)">'
                f'<div style="margin-bottom:8px"><strong>Summary:</strong> {_esc(parsed.get("summary", ""))}</div>'
                f'<div style="margin-bottom:8px"><strong>Type:</strong> '
                f'<code>{_esc(parsed.get("issue_type", "Task"))}</code></div>'
                f'<div style="margin-bottom:8px"><strong>Priority:</strong> '
                f'{_priority_badge(parsed.get("priority", "Medium"))}</div>'
                f'<div style="margin-bottom:8px"><strong>Component:</strong> '
                f'<code>{_esc(parsed.get("component", "General"))}</code></div>'
                f"</div>",
                unsafe_allow_html=True,
            )

            if parsed.get("description"):
                st.markdown("")
                with st.expander("Description", expanded=True):
                    st.text(parsed["description"][:1000])

            triage = parsed.get("triage")
            if triage:
                st.markdown("")
                st.markdown("#### Triage Analysis")
                st.markdown(
                    f'<div style="border:1px solid rgba(139,92,246,.2);border-radius:12px;'
                    f'padding:14px 18px;background:rgba(139,92,246,.04)">'
                    f'<div style="margin-bottom:6px"><strong>Suggested Assignee:</strong> '
                    f'{_esc(triage.get("suggested_assignee", "unassigned"))}</div>'
                    f'<div style="margin-bottom:6px"><strong>Confidence:</strong> '
                    f'{_confidence_bar(triage.get("confidence", 0))}</div>'
                    f'<div style="font-size:.85rem;opacity:.7;margin-top:8px">'
                    f'{_esc(triage.get("reasoning", ""))}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
        elif not created:
            st.info("Enter a description and click **Parse & Preview** to see the structured ticket fields.")


def _esc(text: str) -> str:
    """Minimal HTML escape."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _priority_badge(priority: str) -> str:
    colors = {
        "Highest": "var(--jt-danger)",
        "High": "var(--jt-warning)",
        "Medium": "var(--jt-warning)",
        "Low": "var(--jt-success)",
        "Lowest": "var(--jt-text-muted)",
    }
    color = colors.get(priority, "var(--jt-text-muted)")
    return (
        f'<span style="color:{color};font-weight:700;font-size:.9rem">'
        f"\u25cf {priority}</span>"
    )


def _confidence_bar(confidence: float) -> str:
    pct = int(confidence * 100)
    if confidence >= 0.7:
        color = "var(--jt-success)"
    elif confidence >= 0.4:
        color = "var(--jt-warning)"
    else:
        color = "var(--jt-danger)"
    return (
        f'<span style="font-weight:600;color:var(--jt-text)">{pct}%</span> '
        f'<span style="display:inline-block;width:80px;height:6px;'
        f'background:var(--jt-border);border-radius:3px;vertical-align:middle">'
        f'<span style="display:inline-block;width:{pct}%;height:100%;'
        f'background:{color};border-radius:3px"></span></span>'
    )
