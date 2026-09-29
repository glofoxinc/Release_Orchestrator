"""Release date / fix-version confirmation — Jira-first, user confirm before RN & SHIPIT."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import jira_client
import shipit_test_mode
from generators.release_notes_draft import parse_fix_version_name, version_label_from_deploy_date


def fetch_fix_versions_by_ticket(ticket_keys: list[str]) -> dict[str, list[str]]:
    """Read fixVersions from Jira for each ticket key (metadata only)."""
    out: dict[str, list[str]] = {}
    for key in ticket_keys:
        ticket = str(key or "").strip().upper()
        if not ticket:
            continue
        try:
            issue = jira_client.get_issue(ticket)
            fields = issue.get("fields") or {}
            names = [
                str(v.get("name") or "").strip()
                for v in (fields.get("fixVersions") or [])
                if str(v.get("name") or "").strip()
            ]
            out[ticket] = list(dict.fromkeys(names))
        except Exception:  # noqa: BLE001 — best-effort per ticket
            out[ticket] = []
    return out


def _version_date(name: str) -> date | None:
    return shipit_test_mode.parse_release_version_date(name)


def _default_t_plus_one_version() -> tuple[str, str, date]:
    deploy = date.fromordinal(date.today().toordinal() + 1)
    version_label, date_label = version_label_from_deploy_date(deploy)
    return version_label.lstrip("vV"), date_label, deploy


def build_release_date_proposal(
    session: dict[str, Any],
    ticket_keys: list[str],
) -> dict[str, Any]:
    """Propose release version/date — prefer Jira fixVersions, else suggest T+1."""
    inputs = session.get("inputs") or {}
    explicit = str(inputs.get("version_name") or inputs.get("release_version") or "").strip()
    explicit = explicit.lstrip("vV")

    jira_by_ticket = fetch_fix_versions_by_ticket(ticket_keys)
    version_to_keys: dict[str, list[str]] = {}
    for key, names in jira_by_ticket.items():
        for name in names:
            version_to_keys.setdefault(name, []).append(key)

    parsed_versions: dict[str, date] = {}
    for name in version_to_keys:
        parsed = _version_date(name)
        if parsed:
            parsed_versions[name] = parsed

    tplus_version, tplus_label, tplus_date = _default_t_plus_one_version()

    proposal: dict[str, Any] = {
        "ticket_keys_checked": list(jira_by_ticket.keys()),
        "jira_fix_versions_by_ticket": jira_by_ticket,
        "suggested_t_plus_one": {
            "version_name": tplus_version,
            "deploy_date": tplus_date.isoformat(),
            "date_label": tplus_label,
        },
        "needs_user_confirmation": True,
    }

    if explicit:
        explicit_date = _version_date(explicit)
        proposal.update(
            {
                "source": "user_explicit",
                "version_name": explicit,
                "deploy_date": (explicit_date or tplus_date).isoformat(),
                "date_label": (
                    parse_fix_version_name(explicit)[1]
                    if parse_fix_version_name(explicit)
                    else tplus_label
                ),
                "message": f"You entered release version **{explicit}**.",
            }
        )
        return proposal

    if len(parsed_versions) == 1:
        name = next(iter(parsed_versions))
        deploy = parsed_versions[name]
        date_label = parse_fix_version_name(name)[1] if parse_fix_version_name(name) else ""
        proposal.update(
            {
                "source": "jira_consensus",
                "version_name": name.lstrip("vV"),
                "deploy_date": deploy.isoformat(),
                "date_label": date_label,
                "message": (
                    f"All checked tickets share Jira fix version **{name}** "
                    f"({date_label or deploy.isoformat()})."
                ),
            }
        )
        return proposal

    if len(parsed_versions) > 1:
        conflicts = [
            {"version_name": name, "deploy_date": d.isoformat(), "tickets": version_to_keys.get(name, [])}
            for name, d in sorted(parsed_versions.items(), key=lambda x: x[1])
        ]
        proposal.update(
            {
                "source": "jira_conflict",
                "version_name": "",
                "deploy_date": "",
                "conflicting_versions": conflicts,
                "message": (
                    "Tickets have **different** Jira fix versions. "
                    "Reply with one version, e.g. `2026.3.09.18`, then confirm."
                ),
            }
        )
        return proposal

    tickets_with_any = [k for k, names in jira_by_ticket.items() if names]
    tickets_without = [k for k, names in jira_by_ticket.items() if not names]
    proposal.update(
        {
            "source": "no_jira_fix_version",
            "version_name": tplus_version,
            "deploy_date": tplus_date.isoformat(),
            "date_label": tplus_label,
            "tickets_without_fix_version": tickets_without,
            "tickets_with_other_versions": tickets_with_any,
            "message": (
                "No shared Jira fix version found on the selected tickets. "
                f"Suggested default (T+1): **{tplus_version}** ({tplus_label}). "
                "Confirm or send a different `YYYY.Q.MM.DD` version."
            ),
        }
    )
    return proposal


def format_confirmation_prompt(proposal: dict[str, Any]) -> str:
    """Human-readable prompt for the release-date confirmation step."""
    lines = [
        "**Confirm release date** (used for Release Notes filename, SHIPIT window, and Slack).",
        "",
        str(proposal.get("message") or "Confirm the release version and deploy date."),
    ]
    version = str(proposal.get("version_name") or "").strip()
    deploy = str(proposal.get("deploy_date") or "").strip()
    if version:
        lines.append("")
        lines.append(f"- **Release version:** `{version}`")
    if deploy:
        lines.append(f"- **Deploy date:** {deploy}")
    source = str(proposal.get("source") or "")
    if source == "jira_consensus":
        lines.append("- **Source:** Jira fixVersions on locked tickets")
    elif source == "no_jira_fix_version":
        lines.append("- **Source:** Suggested T+1 (not found on all tickets in Jira)")
    elif source == "user_explicit":
        lines.append("- **Source:** You provided the version in chat")
    elif source == "jira_conflict":
        lines.append("- **Source:** Jira — conflicting fix versions (must pick one)")

    by_ticket = proposal.get("jira_fix_versions_by_ticket") or {}
    if by_ticket:
        lines.append("")
        lines.append("**Jira fixVersions per ticket:**")
        for key in sorted(by_ticket.keys()):
            names = by_ticket[key]
            shown = ", ".join(names) if names else "*(none)*"
            lines.append(f"- {key}: {shown}")

    conflicts = proposal.get("conflicting_versions") or []
    if conflicts:
        lines.append("")
        lines.append("**Conflicts:**")
        for row in conflicts:
            tickets = ", ".join(row.get("tickets") or [])
            lines.append(f"- `{row.get('version_name')}` on {tickets}")

    lines.append("")
    lines.append(
        "Reply **yes** to confirm, or send **`2026.3.09.18`** (or another `YYYY.Q.MM.DD`) to override, then **yes**."
    )
    return "\n".join(lines)


def confirmed_inputs(
    inputs: dict[str, Any],
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """Build session inputs after user confirms release date."""
    explicit = str(inputs.get("version_name") or "").strip().lstrip("vV")
    version = explicit or str(proposal.get("version_name") or "").strip().lstrip("vV")
    if not version:
        raise ValueError("Release version is required — set version_name before confirming.")

    deploy = _version_date(version)
    if not deploy:
        deploy_raw = str(proposal.get("deploy_date") or inputs.get("planned_deploy_date") or "").strip()
        if deploy_raw:
            deploy = date.fromisoformat(deploy_raw)
    if not deploy:
        raise ValueError(f"Could not parse deploy date from version '{version}'.")

    iso = deploy.isoformat()
    # Version + deploy date only — SHIPIT schedule times come from deployment profile
    # defaults via _service_schedule (avoid partial schedule fields in validation).
    return {
        "version_name": version,
        "release_version": version,
        "planned_deploy_date": iso,
        "release_date_confirmed": True,
        "release_date_source": str(proposal.get("source") or "user_confirmed"),
    }
