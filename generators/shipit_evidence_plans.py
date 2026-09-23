"""Evidence-based SHIPIT plan builders — gold standard SHIPIT-17036 (Sushma / Customize BI).

Uses Jira-fetched evidence (description + comments) when available; falls back to
ticket metadata. Content is ticket-specific and uses business language.
"""

from __future__ import annotations

from typing import Any

import adf_builder as adf

from service_ticket_plans import consolidate_by_report


def _ticket_refs(ctx: dict) -> str:
    refs = [
        str(entry.get("ticket") or "").strip()
        for entry in ctx.get("extracted") or []
        if str(entry.get("ticket") or "").strip()
    ]
    return ", ".join(dict.fromkeys(refs)) or "the release tickets"


_JIRA_BASE = "https://abcfinancial.atlassian.net/browse"

_STANDARD_EXCLUSIONS = (
    "Production RLS, workspace access, and capacity settings.",
    "Switching to an alternate metric definition not approved on the ticket.",
    "Any other report or dashboard not listed in this release.",
)


def _evidence(entry: dict) -> dict[str, Any]:
    ev = entry.get("evidence")
    return ev if isinstance(ev, dict) else {}


def _entries_with_evidence(extracted: list[dict]) -> list[tuple[dict, dict]]:
    """Map consolidated report groups back to richest evidence on member tickets."""
    out: list[tuple[dict, dict]] = []
    for entry in extracted:
        out.append((entry, _evidence(entry)))
    return out


def _is_custom_only(extracted: list[dict]) -> bool:
    return bool(extracted) and all(e.get("type") == "Custom" for e in extracted)


def _is_analyze_only(extracted: list[dict]) -> bool:
    return bool(extracted) and all(e.get("type") == "Analyze" for e in extracted)


def _is_mixed_release(extracted: list[dict]) -> bool:
    if not extracted:
        return False
    has_analyze = any(e.get("type") == "Analyze" for e in extracted)
    has_custom = any(e.get("type") == "Custom" for e in extracted)
    return has_analyze and has_custom


def _supporting_record_text(entry: dict) -> str:
    """Rich supporting-record line — SHIPIT-17191 style."""
    status = _status_label(entry)
    ev = _evidence(entry)
    extras: list[str] = []
    if ev.get("looker_validation") and ev.get("qa_validator"):
        date = f" ({ev['qa_date']})" if ev.get("qa_date") else ""
        extras.append(f"Looker data validation by {ev['qa_validator']}{date}")
    elif ev.get("qa_validator") and ev.get("qa_date"):
        extras.append(
            f"{ev['qa_validator']} on {ev['qa_date']} "
            f"{ev.get('qa_method', 'validated the change')}"
        )
    elif ev.get("qa_validator"):
        extras.append(
            f"{ev.get('qa_method', 'QA working as expected')} ({ev['qa_validator']})"
        )
    if ev.get("stakeholder_approval"):
        sa = ev["stakeholder_approval"]
        date = f" ({sa['date']})" if sa.get("date") else ""
        extras.append(f"{sa['name']} approved publish to customer-facing{date}")
    if ev.get("product_decision"):
        extras.append(f"Ships as {ev['product_decision']}")
    if extras:
        return f"{status}; {'; '.join(extras)}"
    return status


def _client_label(entry: dict) -> str:
    client = str(entry.get("client") or "").strip()
    if client and client not in ("Standard", "Unknown"):
        return client
    return "Glofox Analyze"


def _deploy_prefix(entry: dict) -> str:
    if entry.get("type") == "Custom":
        return _client_label(entry)
    return "Glofox Analyze"


def _workspace_label(extracted: list[dict]) -> str:
    has_analyze = any(e.get("type") == "Analyze" for e in extracted)
    has_custom = any(e.get("type") == "Custom" for e in extracted)
    for entry in extracted:
        ws = _evidence(entry).get("deploy_workspace")
        if ws:
            return str(ws)
    if has_analyze and has_custom:
        return "Standard (Analyze) and Custom client workspaces"
    if has_analyze:
        return "Glofox Analyze"
    if has_custom:
        if len(extracted) > 1:
            return "customer-facing V2 Fitness BI workspace"
        client = _client_label(extracted[0])
        if client != "Glofox Analyze":
            return client
        return "customer-facing V2 Fitness BI workspace"
    return "impacted workspaces"


def _ticket_link(key: str) -> str:
    return f"{_JIRA_BASE}/{key}"


def _status_label(entry: dict) -> str:
    return str(entry.get("status") or "Release approved").strip()


def _report_label(entry: dict) -> str:
    return str(entry.get("report") or entry.get("description") or "report").strip()


def _concise_change(entry: dict) -> str:
    """Short business summary — never dump full Jira description into SHIPIT plans."""
    ev = _evidence(entry)
    bullets = list(ev.get("change_bullets") or [])
    if bullets:
        return bullets[0].strip().rstrip(".")
    report = _report_label(entry)
    desc = str(entry.get("description") or "").strip()
    if desc and len(desc) <= 100 and "\n" not in desc:
        return desc.rstrip(".")
    if entry.get("type") == "Custom":
        return f"updates to {report}"
    if ev.get("artifact_column"):
        return f"add {ev['artifact_column']}"
    return desc[:100].rstrip(".") if desc else "planned updates"


def _measured_impact_line(extracted: list[dict]) -> str | None:
    """Only when ticket evidence supplies a real metric — no vague CAB filler."""
    for entry in extracted:
        ev = _evidence(entry)
        custom = str(ev.get("measured_impact") or "").strip()
        if custom:
            return f"Measured impact: {custom.rstrip('.')}."
        numeric = str(ev.get("numeric_example") or "").strip()
        if numeric:
            return f"Measured impact: Example on the ticket — {numeric.rstrip('.')}."
    return None


def _cab_exceptions(extracted: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for _, ev in _entries_with_evidence(extracted):
        for item in ev.get("cab_exceptions") or []:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def build_evidence_description_adf(
    extracted: list[dict],
    *,
    version_label: str = "",
    window: dict[str, str] | None = None,
    sharepoint_url: str = "",
    sharepoint_label: str | None = None,
) -> dict:
    """ADF description matching SHIPIT-17036 sections."""
    content: list[dict] = []

    content.append(adf.paragraph(adf.text("What is changing, in business terms", bold=True)))

    used_bullets: set[str] = set()
    for entry in extracted:
        ev = _evidence(entry)
        key = str(entry.get("ticket") or "").strip()
        report = _report_label(entry)
        bullets = list(ev.get("change_bullets") or [])
        if not bullets:
            desc = str(entry.get("description") or "").strip()
            if desc and desc.lower() != report.lower():
                bullets = [desc]
            else:
                bullets = [f"Updates to {report}"]

        client = _client_label(entry)
        for bullet in bullets[:4]:
            text = bullet.strip()
            if text in used_bullets:
                continue
            used_bullets.add(text)
            if entry.get("type") == "Custom" and client and not text.lower().startswith(client.lower()):
                text = f"{client} — {text}"
            suffix = f" ({key})" if key else ""
            content.append(adf.bullet_item(adf.text(f"{text}{suffix}.")))

        if ev.get("dashboard_definition"):
            dash_text = (
                f"On {key}, QA aligned to the Glofox dashboard rule: "
                f"{ev['dashboard_definition']}."
            )
            if dash_text not in used_bullets:
                used_bullets.add(dash_text)
                content.append(adf.bullet_item(adf.text(dash_text)))

        if ev.get("product_decision_gap") and not ev.get("product_decision"):
            gap = str(ev["product_decision_gap"])
            if gap not in used_bullets:
                used_bullets.add(gap)
                content.append(adf.bullet_item(adf.text(gap + ".")))

    content.append(
        adf.bullet_item(
            adf.text(
                "Existing columns (including totals), parameters, filters, and "
                "scheduling/email share are intended to stay unchanged unless a "
                "ticket explicitly requires otherwise."
            ),
        )
    )

    content.append(adf.paragraph(adf.text("Who is affected", bold=True)))
    if len(extracted) == 1 and _is_analyze_only(extracted):
        report = _report_label(extracted[0])
        content.append(
            adf.paragraph(
                adf.text(
                    f"Entitled Glofox Analyze users of {report}, including existing "
                    "subscribers of that report. The ticket does not document an "
                    "affected-user count."
                ),
            )
        )
    elif _is_custom_only(extracted):
        if len(extracted) == 1:
            client = _client_label(extracted[0])
            report = _report_label(extracted[0])
            content.append(
                adf.paragraph(
                    adf.text(
                        f"Entitled {client} users of {report}. "
                        "The ticket does not document an affected-user count."
                    ),
                )
            )
        else:
            audience = ", ".join(
                f"{_client_label(e)} users of {_report_label(e)}" for e in extracted
            )
            content.append(
                adf.paragraph(
                    adf.text(
                        f"Entitled {audience}. "
                        "The tickets do not document an affected-user count."
                    ),
                )
            )
    elif _is_mixed_release(extracted):
        analyze_reports = ", ".join(_report_label(e) for e in extracted if e.get("type") == "Analyze")
        custom_audience = ", ".join(
            f"{_client_label(e)} users of {_report_label(e)}"
            for e in extracted
            if e.get("type") == "Custom"
        )
        content.append(
            adf.paragraph(
                adf.text(
                    f"Entitled Glofox Analyze users of {analyze_reports}, and entitled "
                    f"{custom_audience}. The tickets do not document an affected-user count."
                ),
            )
        )
    else:
        ws = _workspace_label(extracted)
        content.append(
            adf.paragraph(
                adf.text(
                    f"Entitled users of the impacted reports and dashboards in {ws}. "
                    "The release tickets do not document an affected-user count."
                ),
            )
        )

    content.append(adf.paragraph(adf.text("Not included in this change", bold=True)))
    not_included: set[str] = set(_STANDARD_EXCLUSIONS)
    for _, ev in _entries_with_evidence(extracted):
        for item in ev.get("not_included_bullets") or []:
            if str(item).strip():
                not_included.add(str(item).strip())
    for item in sorted(not_included):
        content.append(adf.bullet_item(adf.text(item)))

    content.append(adf.paragraph(adf.text("How it is deployed", bold=True)))
    if len(extracted) == 1 and _is_analyze_only(extracted):
        report = _report_label(extracted[0])
        content.append(
            adf.paragraph(
                adf.text(
                    f"Back up the paginated report and the Production Analyze semantic model. "
                    f"Publish only the updated {report} report to the Glofox Analyze workspace. "
                    "Bind to the existing Production Analyze semantic model. "
                    "Do not change RLS, access, or capacity."
                ),
            )
        )
    elif _is_custom_only(extracted):
        ws = _workspace_label(extracted)
        reports = " and ".join(_report_label(e) for e in extracted)
        backup_phrase = (
            "both reports"
            if len(extracted) > 1
            else f"{reports} report"
        )
        content.append(
            adf.paragraph(
                adf.text(
                    f"Back up the current Production {backup_phrase}. Publish the updated "
                    f"{reports} report{'s' if len(extracted) > 1 else ''} to the {ws}. "
                    "Do not change RLS, access, or capacity."
                ),
            )
        )
    elif _is_mixed_release(extracted):
        content.append(
            adf.paragraph(
                adf.text(
                    "Back up impacted Glofox Analyze paginated reports, dashboards, and semantic "
                    "models, and current Production Custom client reports. Publish updated Analyze "
                    "artifacts to the Glofox Analyze workspace (bind to existing Production Analyze "
                    "semantic model). Publish updated Custom reports to the customer-facing V2 "
                    "Fitness BI workspace. Do not change RLS, access, or capacity."
                ),
            )
        )
    else:
        ws = _workspace_label(extracted)
        content.append(
            adf.paragraph(
                adf.text(
                    f"Back up impacted paginated reports, dashboards, and semantic models. "
                    f"Publish updated artifacts to {ws}. Bind to existing production semantic "
                    "models. Do not change RLS, access, or capacity."
                ),
            )
        )

    content.append(adf.paragraph(adf.text("Supporting records", bold=True)))
    for entry in extracted:
        key = str(entry.get("ticket") or "").strip()
        if not key:
            continue
        detail = _supporting_record_text(entry)
        content.append(
            adf.bullet_item(
                adf.link(key, _ticket_link(key)),
                adf.text(f" — {detail}"),
            )
        )
    if window and window.get("sentence"):
        content.append(adf.bullet_item(adf.text(f"Planned window: {window['sentence']}")))
    elif version_label:
        content.append(adf.bullet_item(adf.text(f"Release version: {version_label.lstrip('v')}")))
    sp = str(sharepoint_url or "").strip()
    if sp:
        label = sharepoint_label or f"Release Notes {version_label.lstrip('v')}.docx"
        content.append(adf.bullet_item(adf.link(label, sp)))

    return adf.doc(*content)


def build_evidence_business_impact(ctx: dict) -> str:
    """Before / After / Audience / Measured impact — SHIPIT-17036 pattern."""
    extracted = ctx.get("extracted") or []
    lines: list[str] = []

    if len(extracted) == 1:
        entry = extracted[0]
        ev = _evidence(entry)
        report = _report_label(entry)
        col = ev.get("artifact_column") or entry.get("description") or "the planned change"
        key = str(entry.get("ticket") or "").strip()
        lines.append(
            f"This release adds {col} to the existing Glofox Analyze paginated report "
            f"{report} so entitled operators can see the updated metric next to existing "
            f"columns they already use ({key})."
        )
    else:
        entries = consolidate_by_report(extracted)
        refs = _ticket_refs(ctx)
        if _is_custom_only(extracted):
            parts = []
            for entry in extracted:
                client = _client_label(entry)
                report = _report_label(entry)
                key = str(entry.get("ticket") or "").strip()
                change = _concise_change(entry)
                parts.append(f"{client} {report} ({change}; {key})")
            lines.append(
                "This release deploys "
                + "; ".join(parts)
                + ", so entitled operators see the agreed results on the customer-facing reports."
            )
        elif _is_mixed_release(extracted):
            parts = []
            for entry in extracted:
                key = str(entry.get("ticket") or "").strip()
                if entry.get("type") == "Analyze":
                    report = _report_label(entry)
                    col = _evidence(entry).get("artifact_column") or _concise_change(entry)
                    parts.append(f"Glofox Analyze {report} ({col}; {key})")
                else:
                    client = _client_label(entry)
                    report = _report_label(entry)
                    change = _concise_change(entry)
                    parts.append(f"{client} {report} ({change}; {key})")
            lines.append(
                "This release deploys " + "; ".join(parts) + "."
            )
        else:
            labels = ", ".join(e["label"] for e in entries)
            lines.append(
                f"This release improves data accuracy, report usability, and dashboard "
                f"availability across {_workspace_label(extracted)} ({refs})."
            )
            lines.append(f"Impacted reports: {labels}.")

    lines.append("")
    if len(extracted) == 1 and _evidence(extracted[0]).get("before_state"):
        lines.append(f"Before: {_evidence(extracted[0])['before_state']}")
    elif len(extracted) > 1 and any(_evidence(e).get("before_state") for e in extracted):
        before_parts = [
            _evidence(e)["before_state"]
            for e in extracted
            if _evidence(e).get("before_state")
        ]
        lines.append(f"Before: {' '.join(before_parts)}")
    else:
        lines.append(
            "Before: Operators use the current production versions without these changes."
        )

    lines.append("")
    if len(extracted) == 1 and _evidence(extracted[0]).get("after_state"):
        after = _evidence(extracted[0])["after_state"]
        num = _evidence(extracted[0]).get("numeric_example")
        if num:
            after += f" Example on the ticket: {num}."
        lines.append(f"After: {after}")
    elif len(extracted) > 1 and any(_evidence(e).get("after_state") for e in extracted):
        after_parts = [
            _evidence(e)["after_state"]
            for e in extracted
            if _evidence(e).get("after_state")
        ]
        lines.append(f"After: {' '.join(after_parts)}")
    else:
        lines.append(
            "After: Updated reports and dashboards reflect the ticket deliverables above."
        )

    lines.append("")
    if len(extracted) == 1 and _is_analyze_only(extracted):
        report = _report_label(extracted[0])
        lines.append(
            f"Audience and boundary: Entitled Glofox Analyze users of {report}, "
            "including existing subscribers. Other Analyze reports, RLS, workspace "
            "access, and capacity are unchanged."
        )
    elif _is_custom_only(extracted):
        audience = ", ".join(
            f"{_client_label(e)} users of {_report_label(e)}" for e in extracted
        )
        lines.append(
            f"Audience and boundary: Entitled {audience}. "
            "Other reports, RLS, workspace access, and capacity are unchanged."
        )
    elif _is_mixed_release(extracted):
        analyze_reports = ", ".join(_report_label(e) for e in extracted if e.get("type") == "Analyze")
        custom_audience = ", ".join(
            f"{_client_label(e)} users of {_report_label(e)}"
            for e in extracted
            if e.get("type") == "Custom"
        )
        lines.append(
            f"Audience and boundary: Entitled Glofox Analyze users of {analyze_reports}, and "
            f"{custom_audience}. Other reports, RLS, workspace access, and capacity are unchanged."
        )
    else:
        lines.append(
            "Audience and boundary: Entitled users of the listed reports and dashboards. "
            "Other reports, RLS, workspace access, and capacity are unchanged unless "
            "a ticket explicitly requires otherwise."
        )

    measured = _measured_impact_line(extracted)
    if measured:
        lines.append("")
        lines.append(measured)
    lines.append("")
    lines.append(f"Ticket: {_ticket_refs(ctx)}.")
    return "\n".join(lines)


def build_evidence_implementation(ctx: dict) -> str:
    """Implementation Steps (customfield_11720) — SHIPIT-17036 pattern."""
    extracted = ctx.get("extracted") or []
    ws = _workspace_label(extracted)
    if _is_mixed_release(extracted):
        backup_line = (
            "Take backups of impacted Glofox Analyze paginated reports, dashboards, and "
            "semantic models, and current Production Custom client reports before deployment."
        )
        deploy_line = (
            "Deploy updated reports to Glofox Analyze and customer-facing V2 Fitness BI "
            "workspace as applicable per ticket below."
        )
    elif _is_custom_only(extracted) and len(extracted) > 1:
        report_names = " and ".join(_report_label(e) for e in extracted)
        backup_line = (
            f"Take backups of the current Production {report_names} reports before deployment."
        )
        deploy_line = f"Deploy updated reports to the {ws}."
    else:
        backup_line = (
            f"Take backups of all impacted Power BI paginated reports and semantic models "
            f"in the {ws} workspace before deployment."
        )
        deploy_line = f"Deploy updated reports to the {ws}."
    lines = [
        "Pre-deployment backups",
        backup_line,
        "",
        deploy_line,
    ]

    for entry in extracted:
        ev = _evidence(entry)
        key = str(entry.get("ticket") or "").strip()
        report = _report_label(entry)
        col = ev.get("artifact_column")
        change = str(entry.get("description") or "").strip() or "planned updates"
        prefix = _deploy_prefix(entry)
        if col and entry.get("type") == "Analyze":
            detail = (
                f"publish the updated {report} paginated report with the new {col} column, "
                "bind to the Production Analyze semantic model, and keep existing parameters, "
                "filters, and scheduling/email share enabled by default"
            )
            if ev.get("dashboard_definition"):
                detail += (
                    f". {col} uses the Glofox dashboard definition "
                    f"({ev['dashboard_definition']})"
                )
            detail += ". Do not change other columns or report behavior beyond this addition."
        elif ev.get("looker_validation"):
            detail = (
                f"publish the updated {report} report with Looker-aligned class filters "
                f"({change}). Keep existing parameters and unrelated filters unchanged "
                "beyond this enhancement."
            )
        elif ev.get("test_cases"):
            detail = (
                f"publish the updated {report} with the approved group/location filter logic "
                f"({change}). Keep existing parameters and unrelated filters unchanged."
            )
        elif entry.get("type") == "Custom":
            detail = (
                f"publish the updated {report} with {change}. Keep existing parameters and "
                "unrelated filters unchanged beyond this enhancement."
            )
        else:
            detail = (
                f"publish the updated {report} with {change}. Bind to the production "
                "semantic model and keep existing parameters, filters, and scheduling "
                "enabled by default"
            )
        lines.append(f"{prefix} ({key}): {detail}")

    lines.append(
        "Do not change Production RLS, workspace access, or capacity settings "
        "unless explicitly required by a ticket in this release."
    )
    return "\n\n".join(lines)


def _build_custom_verification_steps(extracted: list[dict]) -> list[str]:
    """Per-ticket verification checklist — SHIPIT-17191 multi-custom pattern."""
    lines: list[str] = []
    step = 1
    for entry in extracted:
        ev = _evidence(entry)
        key = str(entry.get("ticket") or "").strip()
        client = _client_label(entry)
        report = _report_label(entry)
        if ev.get("looker_validation"):
            lines.append(
                f"{step}. {client} ({key}): use an entitled non-admin user; confirm class "
                f"filters match Looker for variations validated in QA on {report}."
            )
            step += 1
            lines.append(
                f"{step}. {client}: confirm existing report behavior outside class filters "
                "is unchanged."
            )
            step += 1
        elif ev.get("test_cases"):
            for tc in ev["test_cases"]:
                lines.append(f"{step}. {client} ({key}): {tc.strip()}.")
                step += 1
        else:
            lines.append(
                f"{step}. {client} ({key}): confirm filters and parameters work as documented "
                f"on {report}."
            )
            step += 1
    lines.append(
        f"{step}. Smoke-test one other existing customer-facing report in the same workspace "
        "is unaffected."
    )
    step += 1
    lines.append(
        f"{step}. Record validator, timestamp, screenshots, expected vs observed, and pass/fail "
        f"for {_ticket_refs({'extracted': extracted})}."
    )
    step += 1
    lines.append(
        f"{step}. Roll back the affected report if filter mismatch, wrong club set, or smoke test fails."
    )
    return lines


def _build_mixed_verification_steps(extracted: list[dict]) -> list[str]:
    """Analyze + Custom combined checklist."""
    lines: list[str] = []
    step = 1
    refs = _ticket_refs({"extracted": extracted})

    for entry in extracted:
        if entry.get("type") != "Analyze":
            continue
        ev = _evidence(entry)
        key = str(entry.get("ticket") or "").strip()
        report = _report_label(entry)
        if ev.get("dashboard_definition"):
            lines.append(
                f"{step}. Glofox Analyze ({key}): reconcile {report} to the Glofox dashboard "
                f"({ev['dashboard_definition']}); prefer a member with multiple same-day visits."
            )
            step += 1
            if ev.get("excel_signoff_gap"):
                lines.append(
                    f"{step}. Glofox Analyze: mandatory Excel/PDF checkout — export was raised on "
                    "the ticket and was not separately signed off."
                )
            else:
                lines.append(
                    f"{step}. Glofox Analyze: export Excel/PDF; confirm new fields present and "
                    "existing columns not truncated."
                )
            step += 1
        else:
            lines.append(
                f"{step}. Glofox Analyze ({key}): confirm {report} fields, filters, and parameters "
                "work as documented."
            )
            step += 1

    for entry in extracted:
        if entry.get("type") != "Custom":
            continue
        ev = _evidence(entry)
        key = str(entry.get("ticket") or "").strip()
        client = _client_label(entry)
        report = _report_label(entry)
        if ev.get("looker_validation"):
            lines.append(
                f"{step}. {client} ({key}): confirm class filters match Looker for variations "
                f"validated in QA on {report}."
            )
            step += 1
            lines.append(
                f"{step}. {client}: confirm existing report behavior outside class filters is unchanged."
            )
            step += 1
        elif ev.get("test_cases"):
            for tc in ev["test_cases"]:
                lines.append(f"{step}. {client} ({key}): {tc.strip()}.")
                step += 1
        else:
            lines.append(
                f"{step}. {client} ({key}): confirm filters and parameters on {report} as documented."
            )
            step += 1

    lines.append(
        f"{step}. Smoke-test one other existing Analyze report and one customer-facing report "
        "in their respective workspaces is unaffected."
    )
    step += 1
    lines.append(
        f"{step}. Record validator, timestamp, screenshots, expected vs observed, and pass/fail "
        f"for {refs}."
    )
    step += 1
    lines.append(
        f"{step}. Roll back the affected report if dashboard/Looker mismatch, wrong club set, "
        "export break, or smoke test fails."
    )
    return lines


def build_evidence_verification(ctx: dict) -> str:
    """Verification Steps (customfield_11721) — numbered post-deploy checklist."""
    extracted = ctx.get("extracted") or []
    if _is_mixed_release(extracted):
        return "\n".join(_build_mixed_verification_steps(extracted))
    if _is_custom_only(extracted) and len(extracted) > 1:
        return "\n".join(_build_custom_verification_steps(extracted))

    entries = consolidate_by_report(extracted)
    report_list = ", ".join(e["label"] for e in entries) or "impacted reports"
    refs = _ticket_refs(ctx)

    reconcile_note = (
        f"Reconcile key values to the companion dashboard or acceptance criteria for "
        f"each ticket ({refs})."
    )
    if len(extracted) == 1:
        ev = _evidence(extracted[0])
        if ev.get("dashboard_definition"):
            reconcile_note = (
                f"Reconcile to the Glofox dashboard for at least two members and one period. "
                f"Prefer a member with multiple visits on the same day. "
                f"Daily unique visits must match the dashboard "
                f"({ev['dashboard_definition']})."
            )
            if ev.get("product_decision_gap") and not ev.get("product_decision"):
                reconcile_note += (
                    " Do not treat Analytics event-based counts as the expected result "
                    "unless Product later selects Option A."
                )
        elif ev.get("looker_validation"):
            reconcile_note = (
                f"Confirm class filters match Looker for variations validated in QA on {report_list}."
            )
        elif ev.get("test_cases"):
            reconcile_note = "Re-run ticket test cases in production: " + "; ".join(ev["test_cases"]) + "."

    excel_note = (
        "Export Excel (and PDF if used): new fields are present; existing columns "
        "are not truncated."
    )
    if any(_evidence(e).get("excel_signoff_gap") for e in extracted):
        excel_note += (
            " Excel was raised on the ticket and was not separately signed off. "
            "This checkout is mandatory."
        )
    else:
        excel_note += " Excel/PDF checkout is mandatory before closing tickets."

    smoke_target = (
        "customer-facing report"
        if _is_custom_only(extracted)
        else "Analyze smoke test"
    )
    lines = [
        f"1. Use a non-admin user entitled to {report_list}.",
        "2. Confirm new or updated fields, filters, and parameters work as documented.",
        f"3. {reconcile_note}",
        "4. Confirm Total values and other existing columns not in scope are unchanged.",
        f"5. {excel_note}",
        "6. If the report has subscriptions, confirm an existing or test schedule still delivers.",
        "7. Record validator, timestamp, screenshots, expected vs observed, and pass/fail.",
        f"8. Roll back if dashboard mismatch, missing column, export break, schedule failure, "
        f"or an existing {smoke_target} fails.",
    ]
    return "\n".join(lines)


def build_evidence_rollback(ctx: dict) -> str:
    """Rollback Steps (customfield_11722) — SHIPIT-17036 pattern."""
    extracted = ctx.get("extracted") or []
    ws = _workspace_label(extracted)
    refs = _ticket_refs(ctx)
    if _is_mixed_release(extracted) or (_is_custom_only(extracted) and len(extracted) > 1):
        lines = [
            "If verification fails, halt further publishes and restore the failed report "
            "from the pre-deployment backup.",
            f"Republish the previous {' and/or '.join(_report_label(e) for e in extracted)} "
            "report as needed.",
        ]
    elif _is_custom_only(extracted):
        lines = [
            "If verification fails, halt further publishes and restore the failed report "
            "from the pre-deployment backup.",
            f"Republish the previous {_report_label(extracted[0])} report as needed.",
        ]
    else:
        lines = [
            f"If verification fails, halt the {ws} deploy and restore from the pre-deployment backups.",
        ]
        for entry in extracted:
            ev = _evidence(entry)
            report = _report_label(entry)
            col = ev.get("artifact_column")
            reverse = f"without {col}" if col else f"reverse {entry.get('description') or 'this change'}"
            key = str(entry.get("ticket") or "").strip()
            lines.append(
                f"Republish the previous {report} ({reverse}). Restore the previous Analyze "
                f"semantic model only if the model was updated and is causing the failure ({key})."
            )

    smoke = (
        "customer-facing report"
        if _is_custom_only(extracted) or _is_mixed_release(extracted)
        else "Analyze report"
    )
    lines.extend([
        f"Smoke-test the restored report and one other existing {smoke}.",
        f"Notify stakeholders, set deployment status to Rolled back, comment on {refs}, "
        "and keep the failed package out of Production until a retested build is ready. "
        "No data migration or deletion is in scope. No RLS or access rollback is expected.",
    ])
    return "\n\n".join(lines)


def build_evidence_communication(ctx: dict) -> str:
    """Communication Plan — Pre / During / After success / After rollback."""
    extracted = ctx.get("extracted") or []
    ws = _workspace_label(extracted)
    refs = _ticket_refs(ctx)

    approval_notes: list[str] = []
    for entry in extracted:
        ev = _evidence(entry)
        key = str(entry.get("ticket") or "").strip()
        if ev.get("looker_validation"):
            approval_notes.append(f"Looker validation for {key}")
        if ev.get("stakeholder_approval"):
            sa = ev["stakeholder_approval"]
            approval_notes.append(f"{sa['name']} approve-to-publish for {key}")

    if _is_mixed_release(extracted):
        pre_confirm = f"Confirm Pass QA / Ready for Release on {refs}"
        if approval_notes:
            pre_confirm += f" ({'; '.join(approval_notes)})"
        announce = "No mass client or Analyze announcement is required before go-live."
    elif _is_custom_only(extracted):
        pre_confirm = f"Confirm Ready for Release / publish approval on {refs}"
        if approval_notes:
            pre_confirm += f" ({'; '.join(approval_notes)})"
        announce = "No mass client announcement is required before go-live."
    else:
        pre_confirm = f"Confirm Pass QA on {refs}, {ws} as the only workspace"
        if len(extracted) == 1:
            ev = _evidence(extracted[0])
            if ev.get("product_decision"):
                pre_confirm += f", and written acceptance that deliverables ship as {ev['product_decision']}"
            elif ev.get("product_decision_gap"):
                pre_confirm += (
                    ", and written acceptance of ticket deliverables because Product has "
                    "not replied to open definition questions on the ticket"
                )
            else:
                pre_confirm += ", and written acceptance of ticket deliverables"
        else:
            pre_confirm += ", and written acceptance of ticket deliverables"
        announce = "No mass Analyze-client announcement is required before go-live."

    if _is_mixed_release(extracted) or (_is_custom_only(extracted) and len(extracted) > 1):
        after_success = (
            "Notify stakeholders when verification checklists pass for all impacted reports. "
            "Then share Product/CSM release notes."
        )
    else:
        after_success = (
            "Notify stakeholders when validation is complete, a dashboard sample has been "
            "reconciled, and Excel/PDF checkout is recorded. Then share Product/CSM release notes."
        )

    lines = [
        "Pre-deployment",
        f"Notify the insights-customize-squad channel for the production window. "
        f"{pre_confirm}. {announce}",
        "",
        "During deployment",
        (
            "Post start and completion status and capture Deployment ID and time for each "
            "report publish. Stop further publishes if a deploy fails and alert the Release "
            "Owner immediately."
            if _is_mixed_release(extracted)
            or (_is_custom_only(extracted) and len(extracted) > 1)
            else f"Post start and completion status and capture Deployment ID and time for {ws}. "
            "Stop further publishes if the deploy fails and alert the Release Owner immediately."
        ),
        "",
        "After success",
        after_success,
        "",
        "After rollback",
        "Notify the same channel: changes are not in Production, previous versions are "
        "restored, and the failed artifact stays out of Production until retested.",
    ]
    return "\n\n".join(lines)


def build_evidence_risks(ctx: dict) -> str:
    """Risks Management (customfield_17225) — SHIPIT-17036 pattern."""
    extracted = ctx.get("extracted") or []
    entries = consolidate_by_report(extracted)
    refs = _ticket_refs(ctx)
    labels = ", ".join(e["label"] for e in entries) or "impacted reports"
    cab = _cab_exceptions(extracted)

    gap_notes = []
    if any(_evidence(e).get("product_decision_gap") and not _evidence(e).get("product_decision") for e in extracted):
        gap_notes.append("Product has not confirmed Option A vs Option B on the ticket")
    if any(_evidence(e).get("performance_testing_gap") for e in extracted):
        gap_notes.append("performance testing was not performed/documented")
    gap_text = ". ".join(gap_notes)
    if gap_text:
        gap_text = f" {gap_text}. Residual definition risk is therefore unquantified."

    if _is_mixed_release(extracted):
        overall_modes = (
            "Analyze dashboard mismatch, Custom class-filter parity miss vs Looker, "
            "incorrect group/location club sets, and publish to the wrong workspace"
        )
        overall_controls = (
            "pre-deploy backup, dashboard/Looker reconciliation, TC cases where documented, "
            "stop on first failure, restore only the failed artifact"
        )
    elif _is_custom_only(extracted) and len(extracted) > 1:
        overall_modes = (
            "class-filter parity miss vs Looker, incorrect group/location club sets, "
            "and publish to the wrong workspace"
        )
        overall_controls = (
            "pre-deploy backup, Looker/QA reconciliation, TC-01–03 for Sales League, "
            "stop on first failure, restore only the failed report"
        )
    else:
        overall_modes = (
            "values not matching what Product or clients expect, Excel/PDF layout break "
            "from new fields, semantic-model bind issues, and impact on existing subscribers"
        )
        overall_controls = (
            "pre-deploy backup, dashboard sample reconciliation, mandatory Excel checkout, "
            "stop on first failure, restore affected artifacts only"
        )

    lines = [
        "Overall",
        f"This change is limited to {labels}. Primary failure modes are {overall_modes}. "
        f"Controls: {overall_controls}.{gap_text} "
        "Do not describe residual risk as low.",
        "",
    ]

    for entry in extracted:
        ev = _evidence(entry)
        key = str(entry.get("ticket") or "").strip()
        report = _report_label(entry)
        col = ev.get("artifact_column") or "deployed change"
        client = _client_label(entry)

        if ev.get("looker_validation"):
            lines.extend([
                f"{client} class filters ({key})",
                "Failure mode: filters still miss Looker variations or over-match unrelated classes. "
                "Business effect: Course Offering by location class counts diverge from Looker. "
                "Preventive control: QA validation vs Looker. "
                "Detective control: production sample vs Looker. "
                "Rollback trigger: mismatch vs Looker or stakeholder reject.",
                "",
            ])
            continue

        if ev.get("test_cases"):
            lines.extend([
                f"{client} filter logic ({key})",
                "Failure mode: group selection still expands incorrectly when Location is multi-selected "
                "across groups, or group-selected behavior regresses. "
                "Business effect: Sales League shows wrong clubs. "
                "Preventive control: TC-01–03 and stakeholder approve-to-publish. "
                "Detective control: production re-run of TC-01–03. "
                "Rollback trigger: any TC fail.",
                "",
            ])
            continue

        if ev.get("dashboard_definition") or ev.get("product_decision_gap"):
            lines.extend([
                f"{col} definition ({key})",
                "Failure mode: the column uses one visit per calendar day while Product/clients "
                "expect event-based unique visits, or the reverse. Business effect: figures can "
                f"differ sharply ({ev.get('numeric_example', 'see ticket example')}). "
                "Preventive control: QA vs Glofox dashboard. "
                f"Gap: {ev.get('product_decision_gap') or 'none noted'}. "
                "Detective control: production sample vs dashboard, including a member with "
                "multiple same-day visits. Rollback trigger: values do not match the dashboard, "
                "or Product rejects the daily-unique rule after go-live.",
                "",
            ])

        if ev.get("excel_signoff_gap") or col:
            lines.extend([
                "Layout and export",
                "Failure mode: the added column truncates or drops fields on Excel/PDF. "
                "Business effect: ad-hoc or scheduled extracts are incomplete. "
                "Preventive control: Excel screenshot was raised on the ticket; Excel may not "
                "be separately signed off. Detective control: production Excel/PDF checkout. "
                "Rollback trigger: truncation, missing new column, or missing existing columns "
                "on export.",
                "",
            ])
            break  # one layout section per release

    stop_action = (
        "Stop further publishes on first failure"
        if _is_custom_only(extracted)
        else f"Stop the {_workspace_label(extracted)} deploy on first failure"
    )
    lines.extend([
        "Shared controls",
        f"Do not change Production RLS, workspace access, or capacity. {stop_action} and alert "
        f"the Release Owner. Do not close {refs} or notify Product/CSM until verification passes.",
    ])
    if cab:
        lines.append("")
        lines.append("CAB exceptions on this request: " + "; ".join(cab) + ".")
    return "\n".join(lines)


def build_qa_evidence_test_plan(ctx: dict) -> str:
    """Test plan (customfield_11762) — QA evidence summary paragraph."""
    extracted = ctx.get("extracted") or []
    parts: list[str] = []

    for entry in extracted:
        ev = _evidence(entry)
        key = str(entry.get("ticket") or "").strip()
        status = _status_label(entry)

        if ev.get("qa_validator") and ev.get("qa_date"):
            segment = (
                f"{key} {status}. {ev['qa_validator']} on {ev['qa_date']} "
                f"{ev.get('qa_method', 'validated the change')}."
            )
        elif ev.get("qa_validator"):
            segment = (
                f"{key} {status}. {ev['qa_validator']} "
                f"{ev.get('qa_method', 'validated the change')}."
            )
        else:
            assignee = str(entry.get("assignee") or "").strip()
            report = _report_label(entry)
            segment = f"{key} {status}."
            if assignee:
                segment = f"{key} {status}. {assignee} validated {report}."

        if ev.get("product_decision_gap") and not ev.get("product_decision"):
            segment += " Product has not replied to Option A vs B."
        if ev.get("excel_signoff_gap"):
            segment += " Excel export was requested and not separately signed off."
        if ev.get("stakeholder_approval"):
            sa = ev["stakeholder_approval"]
            date_bit = f" ({sa['date']})" if sa.get("date") else ""
            segment += f" {sa['name']}{date_bit} {sa.get('note', 'approved publish')}."

        parts.append(segment.strip())

    body = " ".join(parts) if parts else "QA sign-off pending on release tickets."
    perf_gap = any(_evidence(e).get("performance_testing_gap") for e in extracted)
    if perf_gap:
        body += " Performance testing: Not performed/documented. Residual performance risk is unquantified."
    else:
        body += (
            " Performance testing: Not performed/documented unless noted on the ticket. "
            "Residual performance risk is unquantified."
        )
    body += " No dedicated regression ticket unless noted on the ticket."
    return body.strip()


def evidence_plan_context(
    extracted: list[dict],
    sharepoint: str,
    version_label: str,
    window: dict[str, str] | None = None,
    *,
    workspaces: str | None = None,
    scope_str: str | None = None,
    dashboards: list[str] | None = None,
    ticket_key: str | None = None,
) -> dict[str, Any]:
    """Build context dict for evidence plan builders."""
    ws = workspaces or _workspace_label(extracted)
    dash = dashboards or [e.get("report") or e.get("description") for e in extracted]
    return {
        "extracted": extracted,
        "sharepoint": sharepoint,
        "version": version_label.lstrip("v"),
        "window": window or {},
        "workspaces": ws,
        "scope_str": scope_str or ws,
        "dashboards": [d for d in dash if d],
        "ticket_key": ticket_key,
    }
