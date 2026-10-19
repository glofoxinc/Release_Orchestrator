"""Release-role Slack + Outlook notices (owners, testers, review, missing fix versions).

Ignite / any operator: same MCP tools. Live send is dry_run until confirmed.
Sushma notices always open with ``Release orchestrator:``.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

import config
from generators.release_notes_test_by import assign_change_table_testers, person_name_matches
from slack_assignee_notify import lookup_user_id_by_email, send_dm

import outlook_mail


ORCHESTRATOR_BANNER = "Release orchestrator:"


def with_orchestrator_banner(text: str) -> str:
    body = (text or "").strip()
    if body.lower().startswith("release orchestrator:"):
        return body
    return f"{ORCHESTRATOR_BANNER}\n\n{body}"


def with_orchestrator_subject(subject: str) -> str:
    title = (subject or "").strip()
    if title.lower().startswith("release orchestrator:"):
        return title
    return f"{ORCHESTRATOR_BANNER} {title}".strip()


def _notify_cfg() -> dict[str, Any]:
    return dict(getattr(config, "RELEASE_NOTIFY", {}) or {})


def _fix_version_owner() -> dict[str, str]:
    raw = _notify_cfg().get("fix_version_owner") or {}
    name = str(raw.get("name") or config.RELEASE_META.get("senior_mgr") or "Sushma Bhamidipati")
    slack_id = str(raw.get("slack_user_id") or "")
    email_env = str(raw.get("email_env") or "RELEASE_NOTIFY_SUSHMA_EMAIL")
    email = str(raw.get("email") or os.environ.get(email_env) or "").strip()
    if not slack_id:
        slack_id = str(((config.SLACK_ANNOUNCE.get("cc") or {}).get("sushma") or {}).get("user_id") or "")
    return {"name": name, "slack_user_id": slack_id, "email": email}


def _ticket_line(row: dict[str, Any]) -> str:
    key = str(row.get("ticket") or row.get("key") or "").strip()
    summary = str(row.get("summary") or "").strip()
    link = str(row.get("link") or "")
    if link:
        return f"{key} — {summary}\n{link}"
    return f"{key} — {summary}"


def _with_test_by(extracted: list[dict[str, Any]], version_name: str) -> list[dict[str, Any]]:
    rows = [dict(r) for r in extracted]
    names = assign_change_table_testers(rows, release_seed=version_name)
    for row, name in zip(rows, names):
        if not str(row.get("test_by") or "").strip():
            row["test_by"] = name
    return rows


def _deployment_owner(extracted: list[dict[str, Any]], *, owner_name: str = "", owner_email: str = "") -> dict[str, str]:
    if owner_name.strip() or owner_email.strip():
        return {
            "name": owner_name.strip() or "Deployment owner",
            "email": owner_email.strip(),
            "slack_user_id": "",
        }
    meta_name = str(config.RELEASE_META.get("release_owner") or "").strip()
    email = ""
    slack_id = ""
    for row in extracted:
        if meta_name and person_name_matches(str(row.get("assignee") or ""), meta_name):
            email = str(row.get("assignee_email") or "")
            break
    return {"name": meta_name or "Deployment owner", "email": email, "slack_user_id": slack_id}


def testers_from_notes(extracted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for row in extracted:
        raw = str(row.get("test_by") or "").strip()
        if not raw:
            continue
        for part in raw.replace("/", ",").split(","):
            name = part.strip()
            if not name:
                continue
            bucket = by_name.setdefault(
                name,
                {"name": name, "email": "", "tickets": []},
            )
            bucket["tickets"].append(row)
            if not bucket["email"]:
                for other in extracted:
                    if person_name_matches(str(other.get("assignee") or ""), name):
                        bucket["email"] = str(other.get("assignee_email") or "")
                        break
    return list(by_name.values())


def _when_label(when: str) -> str:
    return (when or "").strip() or "the next safe deploy day"


def _owner_message(
    version_name: str,
    shipit_key: str,
    tickets: list[dict[str, Any]],
    *,
    when: str = "",
) -> str:
    keys = ", ".join(str(r.get("ticket") or "") for r in tickets if r.get("ticket"))
    shipit = f" SHIPIT {shipit_key}." if shipit_key else ""
    return (
        f"You are the deployment owner for the Glofox / Insights release "
        f"{version_name} on {_when_label(when)}.{shipit}\n\n"
        f"Please own the SHIPIT ticket and deployment window.\n\n"
        f"Tickets:\n" + "\n".join(_ticket_line(r) for r in tickets) + (f"\n\nKeys: {keys}" if keys else "")
    )


def _tester_message(version_name: str, tester: dict[str, Any], *, when: str = "") -> str:
    tickets = tester.get("tickets") or []
    return (
        f"You are a tester for the Glofox / Insights release {version_name} "
        f"on {_when_label(when)}.\n\n"
        f"Please complete QA for your assigned tickets:\n"
        + "\n".join(_ticket_line(r) for r in tickets)
    )


def _sushma_ship_ahead_message(
    version_name: str,
    shipit_key: str,
    *,
    when: str = "",
    ticket_count: int = 0,
    sharepoint_url: str = "",
    client_sharepoint_url: str = "",
) -> str:
    ship = (shipit_key or "").strip()
    shipit_line = f"SHIPIT: {ship}\n" if ship else "SHIPIT: not created yet — please create / confirm.\n"
    n = f"{ticket_count} ticket(s) linked on this SHIPIT.\n" if ticket_count else ""
    notes = ""
    if (sharepoint_url or "").strip():
        notes += f"Release notes: {sharepoint_url.strip()}\n"
    if (client_sharepoint_url or "").strip():
        notes += f"Client notes: {client_sharepoint_url.strip()}\n"
    return (
        f"Hi Sushma — Glofox / Insights daily ship {version_name} is scheduled for "
        f"{_when_label(when)}.\n\n"
        f"{shipit_line}"
        f"Fix Version: {version_name}\n"
        f"{n}"
        f"{notes}"
        "You get this whenever a SHIPIT is created — not as assignee or tester.\n"
        "Fix Versions below are only the tickets linked on this SHIPIT."
    )


def _review_message(
    version_name: str,
    *,
    when: str,
    tickets: list[dict[str, Any]],
) -> str:
    when_line = f" when: {when}" if when else " tomorrow"
    return (
        f"Your tickets are on the review call{when_line} for release {version_name}.\n\n"
        + "\n".join(_ticket_line(r) for r in tickets)
    )


def _sushma_missing_fix_version_message(version_name: str, tickets: list[dict[str, Any]]) -> str:
    """Backward-compatible wrapper — blank Fix Versions only."""
    buckets = {
        "missing": tickets,
        "past": [],
        "future": [],
        "unknown": [],
        "ok": [],
    }
    return _sushma_fix_version_audit_message(version_name, buckets)


def _fix_version_names(row: dict[str, Any]) -> list[str]:
    names = row.get("fix_versions")
    if isinstance(names, list):
        return [str(n).strip() for n in names if str(n).strip()]
    one = str(row.get("fix_version") or "").strip()
    return [one] if one else []


def classify_fix_version(row: dict[str, Any], target_version: str) -> str:
    """ok | missing | past | future | unknown relative to this ship's version."""
    from datetime import date

    from shipit_test_mode import parse_release_version_date

    target = (target_version or "").strip()
    names = _fix_version_names(row)
    if not names:
        return "missing"
    if not target:
        return "ok"
    target_norm = target.lstrip("vV")
    if any(n.lstrip("vV") == target_norm for n in names):
        return "ok"
    target_day = parse_release_version_date(target)
    parsed: list[date] = []
    unparsed = 0
    for name in names:
        day = parse_release_version_date(name)
        if day is None:
            unparsed += 1
        else:
            parsed.append(day)
    if target_day and parsed and unparsed == 0:
        if all(d < target_day for d in parsed):
            return "past"
        if all(d > target_day for d in parsed):
            return "future"
    return "unknown"


def _sushma_fix_version_audit_message(
    version_name: str,
    buckets: dict[str, list[dict[str, Any]]],
    *,
    shipit_key: str = "",
) -> str:
    target = (version_name or "").strip() or "(this ship's version)"
    ship = (shipit_key or "").strip()
    problems = (
        (buckets.get("missing") or [])
        + (buckets.get("past") or [])
        + (buckets.get("future") or [])
        + (buckets.get("unknown") or [])
    )
    ok_rows = buckets.get("ok") or []
    checked = len(ok_rows) + len(problems)
    shipit_line = f"SHIPIT: {ship}." if ship else "SHIPIT: not on this mail — confirm it exists."
    if not checked:
        return (
            f"Hi Sushma — Glofox Fix Version check for {target}.\n"
            f"{shipit_line}\n\n"
            "No tickets are linked on this SHIPIT yet. "
            f"Please create Fix Version {target} if it does not exist, "
            "link the ship tickets, and confirm."
        )
    if problems:
        intro = (
            f"Hi Sushma — Glofox Fix Version check for {target} ({checked} ticket(s)).\n"
            f"{shipit_line}\n\n"
            f"Please create {target} if it does not exist, set the listed tickets onto it, and approve."
        )
    else:
        intro = (
            f"Hi Sushma — Glofox Fix Version check for {target} ({checked} ticket(s)).\n"
            f"{shipit_line}\n\n"
            f"All good. Every ticket on this SHIPIT already has Fix Version {target}."
        )
    lines = [intro, ""]

    def _block(title: str, rows: list[dict[str, Any]], why: str) -> None:
        if not rows:
            return
        lines.append(title)
        if why:
            lines.append(why)
        for row in rows:
            current = ", ".join(_fix_version_names(row)) or "(blank)"
            lines.append(f"{_ticket_line(row)}\n  current Fix Version: {current}")
        lines.append("")

    _block(
        f"All good — already on {target}",
        ok_rows,
        "",
    )
    _block(
        "Blank — no Fix Version",
        buckets.get("missing") or [],
        "Unassigned. Please put them on this ship.",
    )
    _block(
        "Earlier version (past — not this ship)",
        buckets.get("past") or [],
        "Assigned before this release date. Please move them to this ship if they belong here.",
    )
    _block(
        "Later version (future — not this ship)",
        buckets.get("future") or [],
        "Assigned after this release date. Please move them to this ship if they belong here.",
    )
    _block(
        "Wrong or unreadable Fix Version",
        buckets.get("unknown") or [],
        "Name does not match this ship and could not be dated. Please set the correct version.",
    )
    return "\n".join(lines).strip()


def _sushma_combined_shipit_message(
    version_name: str,
    buckets: dict[str, list[dict[str, Any]]],
    *,
    shipit_key: str,
    when: str = "",
    sharepoint_url: str = "",
    client_sharepoint_url: str = "",
) -> str:
    header = _sushma_ship_ahead_message(
        version_name,
        shipit_key,
        when=when,
        ticket_count=sum(len(v) for v in buckets.values()),
        sharepoint_url=sharepoint_url,
        client_sharepoint_url=client_sharepoint_url,
    )
    audit = _sushma_fix_version_audit_message(
        version_name,
        buckets,
        shipit_key=shipit_key,
    )
    return f"{header}\n\n—— Fix Versions on this SHIPIT only ——\n\n{audit}"


def _playwright_handoff(
    *,
    name: str,
    email: str,
    slack_user_id: str,
    subject: str,
    text: str,
) -> dict[str, Any]:
    try:
        import browser_automation as ba

        return ba.playwright_sushma_notify_handoff(
            slack_user_id=slack_user_id,
            email=email,
            name=name,
            subject=subject,
            text=text,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _deliver(
    *,
    name: str,
    email: str,
    slack_user_id: str,
    text: str,
    subject: str,
    dry_run: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "email": email,
        "slack_user_id": slack_user_id,
        "subject": subject,
        "message": text,
        "slack": {"ok": False, "dry_run": dry_run},
        "outlook": {"ok": False, "dry_run": dry_run},
    }
    pw = _playwright_handoff(
        name=name,
        email=email,
        slack_user_id=slack_user_id,
        subject=subject,
        text=text,
    )
    result["playwright_handoff"] = pw
    if dry_run:
        result["slack"] = {
            "ok": True,
            "dry_run": True,
            "slack_mcp_handoff": {
                "tool": "slack_send_message",
                "user_id": slack_user_id,
                "text": text,
            },
        }
        result["outlook"] = outlook_mail.send_mail(
            to=[email] if email else [],
            subject=subject,
            body=text,
            dry_run=True,
        )
        result["ok"] = True
        return result

    slack_ok = False
    slack_err = ""
    user_id = slack_user_id
    try:
        if not user_id and email:
            user_id = lookup_user_id_by_email(email)
        if user_id:
            sent = send_dm(user_id, text)
            slack_ok = bool(sent.get("ok"))
            result["slack"] = {**sent, "dry_run": False}
        else:
            slack_err = "No Slack user id or email lookup."
    except Exception as exc:  # noqa: BLE001
        slack_err = str(exc)
    if not slack_ok:
        result["slack"] = {
            "ok": False,
            "dry_run": False,
            "error": slack_err or "Slack send failed",
            "slack_mcp_handoff": {
                "tool": "slack_send_message",
                "user_id": user_id,
                "text": text,
            },
        }

    result["outlook"] = outlook_mail.send_mail(
        to=[email] if email else [],
        subject=subject,
        body=text,
        dry_run=False,
    )
    native_ok = bool(
        result["slack"].get("ok")
        or result["outlook"].get("ok")
        or result["outlook"].get("sent")
    )
    if not native_ok:
        result["slack"]["playwright_fallback"] = True
        result["outlook"]["playwright_fallback"] = True
    result["ok"] = native_ok or bool(pw.get("steps"))
    return result


def notify_owners_and_testers(
    extracted: list[dict[str, Any]],
    *,
    version_name: str,
    shipit_key: str = "",
    owner_name: str = "",
    owner_email: str = "",
    deploy_when: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    import release_calendar as cal

    dates = cal.propose_release_dates()
    when = (deploy_when or "").strip() or f"{dates['deploy_day']} IST"
    rows = _with_test_by(extracted, version_name)
    owner = _deployment_owner(rows, owner_name=owner_name, owner_email=owner_email)
    testers = testers_from_notes(rows)
    owner_text = _owner_message(version_name, shipit_key, rows, when=when)
    owner_out = _deliver(
        name=owner["name"],
        email=owner["email"],
        slack_user_id=owner.get("slack_user_id") or "",
        text=owner_text,
        subject=f"You are deployment owner — {version_name} ({when})",
        dry_run=dry_run,
    )
    tester_out = [
        _deliver(
            name=str(t["name"]),
            email=str(t.get("email") or ""),
            slack_user_id="",
            text=_tester_message(version_name, t, when=when),
            subject=f"You are tester — {version_name} ({when})",
            dry_run=dry_run,
        )
        for t in testers
    ]
    return {
        "ok": True,
        "dry_run": dry_run,
        "version_name": version_name,
        "shipit_key": shipit_key,
        "when": when,
        "dates": dates,
        "owner": owner_out,
        "testers": tester_out,
        "tester_names": [t["name"] for t in testers],
        "sushma": "pinged on SHIPIT create (not as tester/assignee)",
    }


def notify_sushma_on_shipit_created(
    extracted: list[dict[str, Any]],
    *,
    version_name: str,
    shipit_key: str,
    deploy_when: str = "",
    dry_run: bool = True,
    sharepoint_url: str = "",
    client_sharepoint_url: str = "",
) -> dict[str, Any]:
    """One Slack + Outlook: this SHIPIT plus Fix Versions of tickets linked on it."""
    key = (shipit_key or "").strip()
    if not key:
        return {
            "ok": False,
            "error": "SHIPIT not created — Sushma is notified only when a SHIPIT key exists.",
        }
    import release_calendar as cal

    dates = cal.propose_release_dates()
    when = (deploy_when or "").strip() or f"{dates['deploy_day']} IST"
    fv = notify_missing_fix_versions(
        extracted,
        version_name=version_name,
        shipit_key=key,
        dry_run=True,
        deliver=False,
    )
    buckets = fv.get("buckets") or {}
    owner = _fix_version_owner()
    text = with_orchestrator_banner(
        _sushma_combined_shipit_message(
            version_name,
            buckets,
            shipit_key=key,
            when=when,
            sharepoint_url=sharepoint_url,
            client_sharepoint_url=client_sharepoint_url,
        )
    )
    if fv.get("all_good"):
        subject = f"SHIPIT {key} — Fix Versions OK ({version_name})"
    elif (fv.get("missing_count") or 0) + (fv.get("past_count") or 0) + (
        fv.get("future_count") or 0
    ) + (fv.get("unknown_count") or 0):
        subject = f"SHIPIT {key} — Fix Version gaps ({version_name})"
    else:
        subject = f"SHIPIT {key} — {version_name}"
    sent = _deliver(
        name=owner["name"],
        email=owner["email"],
        slack_user_id=owner["slack_user_id"],
        text=text,
        subject=with_orchestrator_subject(subject),
        dry_run=dry_run,
    )
    return {
        "ok": True,
        "dry_run": dry_run,
        "shipit_key": key,
        "version_name": version_name,
        "when": when,
        "scope": "SHIPIT-linked tickets only",
        "ticket_count": len(extracted),
        "all_good": fv.get("all_good"),
        "missing_keys": fv.get("missing_keys") or [],
        "ok_keys": fv.get("ok_keys") or [],
        "combined": sent,
        "fix_versions": fv,
    }


def notify_review_assignees(
    extracted: list[dict[str, Any]],
    *,
    version_name: str,
    when: str = "",
    include_optional: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """QA testers + main Jira assignees only (optional attendees skipped)."""
    del include_optional  # reserved for Teams optional list; never DM optional people
    rows = _with_test_by(extracted, version_name)
    by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
    emails: dict[str, str] = {}
    testers = testers_from_notes(rows)
    for t in testers:
        name = str(t["name"])
        by_person[name].extend(t.get("tickets") or [])
        if t.get("email"):
            emails[name] = str(t["email"])
    for row in rows:
        assignee = str(row.get("assignee") or "").strip()
        if not assignee:
            continue
        by_person[assignee].append(row)
        if row.get("assignee_email"):
            emails[assignee] = str(row["assignee_email"])
    deliveries = []
    for name, tickets in by_person.items():
        deliveries.append(
            _deliver(
                name=name,
                email=emails.get(name, ""),
                slack_user_id="",
                text=_review_message(version_name, when=when, tickets=tickets),
                subject=f"Review call — your tickets ({version_name})",
                dry_run=dry_run,
            )
        )
    return {
        "ok": True,
        "dry_run": dry_run,
        "version_name": version_name,
        "when": when,
        "recipients": deliveries,
        "skipped": "optional attendees are not notified",
    }


def notify_missing_fix_versions(
    tickets: list[dict[str, Any]],
    *,
    version_name: str = "",
    shipit_key: str = "",
    dry_run: bool = True,
    deliver: bool = True,
) -> dict[str, Any]:
    """Classify tickets on this SHIPIT. Optionally Slack + Outlook Sushma."""
    buckets: dict[str, list[dict[str, Any]]] = {
        "missing": [],
        "past": [],
        "future": [],
        "unknown": [],
        "ok": [],
    }
    for row in tickets:
        kind = classify_fix_version(row, version_name)
        buckets.setdefault(kind, []).append(row)
    problems = (
        buckets["missing"] + buckets["past"] + buckets["future"] + buckets["unknown"]
    )
    owner = _fix_version_owner()
    target = version_name or "this ship"
    if problems:
        subject = f"Fix Version mismatch — set {target} + approve"
    elif buckets["ok"]:
        subject = f"Fix Versions OK — {target} (all good)"
    else:
        subject = f"Fix Version check — no tickets found for {target}"
    text = with_orchestrator_banner(
        _sushma_fix_version_audit_message(
            version_name,
            buckets,
            shipit_key=shipit_key,
        )
    )
    sent = None
    if deliver:
        sent = _deliver(
            name=owner["name"],
            email=owner["email"],
            slack_user_id=owner["slack_user_id"],
            text=text,
            subject=with_orchestrator_subject(subject),
            dry_run=dry_run,
        )
    keys = lambda rows: [str(r.get("ticket") or "") for r in rows]
    return {
        "ok": True,
        "dry_run": dry_run,
        "shipit_key": (shipit_key or "").strip(),
        "buckets": buckets,
        "missing_count": len(buckets["missing"]),
        "missing_keys": keys(buckets["missing"]),
        "past_count": len(buckets["past"]),
        "past_keys": keys(buckets["past"]),
        "future_count": len(buckets["future"]),
        "future_keys": keys(buckets["future"]),
        "unknown_count": len(buckets["unknown"]),
        "unknown_keys": keys(buckets["unknown"]),
        "ok_count": len(buckets["ok"]),
        "ok_keys": keys(buckets["ok"]),
        "all_good": not problems and bool(buckets["ok"]),
        "escalation": sent,
    }


REMINDER_MARKER = "Release Orchestrator reminder"
READY_FOR_REVIEW = "ready for review"
READY_FOR_RELEASE = "ready for release"


def developer_comment_rules() -> str:
    """The only comments a developer needs to post for review and release."""
    return (
        f"{REMINDER_MARKER} — comment with exactly one of these phrases:\n"
        f"{READY_FOR_REVIEW}\n"
        f"{READY_FOR_RELEASE}\n"
        "Reply on this Jira ticket only — the orchestrator reads the comment. "
        "No Slack or Teams group follow-up, no links, no Fix Version, no TCKT or SHIPIT status from you."
    )


def build_developer_reminder_adf(
    row: dict[str, Any],
    *,
    version_name: str,
    shipit_key: str = "",
) -> dict[str, Any]:
    from adf_builder import doc, mention, paragraph, text

    name = str(row.get("assignee") or "developer").strip() or "developer"
    account_id = str(row.get("assignee_account_id") or "").strip()
    ticket = str(row.get("ticket") or row.get("key") or "").strip()
    ship = (shipit_key or "").strip()
    where = f"{ship} / {version_name}" if ship else version_name
    intro_bits = []
    if account_id:
        intro_bits.append(mention(name, account_id))
        intro_bits.append(text(f" — {ticket} is included in {where}."))
    else:
        intro_bits.append(text(f"{name} — {ticket} is included in {where}."))
    return doc(
        paragraph(*intro_bits),
        paragraph(text(f"{REMINDER_MARKER} — comment with exactly one of these phrases:")),
        paragraph(text(READY_FOR_REVIEW, bold=True)),
        paragraph(text("or")),
        paragraph(text(READY_FOR_RELEASE, bold=True)),
        paragraph(
            text(
                "Reply on this Jira ticket only — the orchestrator reads the comment. "
                "No Slack or Teams group follow-up, no links, no Fix Version, no TCKT or SHIPIT status from you."
            )
        ),
    )


def _comment_has_reminder(comments: list[dict[str, Any]]) -> bool:
    import jira_client

    marker = REMINDER_MARKER.lower()
    for comment in comments or []:
        body = comment.get("body") if isinstance(comment, dict) else comment
        if marker in jira_client._comment_plain_text(body):
            return True
    return False


def shipit_linked_ticket_keys(shipit_key: str) -> list[str]:
    """PIC/AN (and other product) keys linked to a SHIPIT ticket."""
    import jira_client

    key = (shipit_key or "").strip().upper()
    if not key:
        return []
    issue = jira_client.get_issue(key)
    fields = issue.get("fields") or {}
    found: list[str] = []
    seen: set[str] = set()

    def take(raw: str) -> None:
        k = (raw or "").strip().upper()
        if not k or k == key or k in seen:
            return
        prefix = k.split("-", 1)[0]
        if prefix in {"SHIPIT", "TCKT"}:
            return
        seen.add(k)
        found.append(k)

    for link in fields.get("issuelinks") or []:
        if not isinstance(link, dict):
            continue
        for side in ("inwardIssue", "outwardIssue"):
            take(str((link.get(side) or {}).get("key") or ""))
    for sub in fields.get("subtasks") or []:
        if isinstance(sub, dict):
            take(str(sub.get("key") or ""))
    return found


def remind_shipit_developers(
    extracted: list[dict[str, Any]],
    *,
    version_name: str,
    shipit_key: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Post a reminder on each SHIPIT-included ticket (assignee @mention when known)."""
    import jira_client

    rows = [dict(r) for r in extracted if str(r.get("ticket") or r.get("key") or "").strip()]
    results: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("ticket") or row.get("key") or "").strip().upper()
        preview = developer_comment_rules()
        item: dict[str, Any] = {
            "ticket": key,
            "assignee": str(row.get("assignee") or ""),
            "preview": preview,
            "skipped": False,
        }
        try:
            existing = jira_client.get_issue_comments(key)
        except Exception as exc:  # noqa: BLE001
            item["ok"] = False
            item["error"] = str(exc)
            results.append(item)
            continue
        if _comment_has_reminder(existing):
            item["ok"] = True
            item["skipped"] = True
            item["reason"] = "reminder already posted"
            results.append(item)
            continue
        adf = build_developer_reminder_adf(
            row, version_name=version_name, shipit_key=shipit_key
        )
        if dry_run:
            item["ok"] = True
            item["dry_run"] = True
            item["adf"] = adf
            results.append(item)
            continue
        try:
            posted = jira_client.add_adf_comment(key, adf)
            item["ok"] = True
            item["comment_id"] = (posted or {}).get("id")
        except Exception as exc:  # noqa: BLE001
            item["ok"] = False
            item["error"] = str(exc)
        results.append(item)
    ok = all(r.get("ok") for r in results) if results else True
    return {
        "ok": ok,
        "dry_run": dry_run,
        "version_name": version_name,
        "shipit_key": shipit_key,
        "rules": developer_comment_rules(),
        "tickets": results,
        "posted_or_previewed": len([r for r in results if r.get("ok") and not r.get("skipped")]),
        "skipped": len([r for r in results if r.get("skipped")]),
    }
