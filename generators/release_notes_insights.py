"""Pre-flight readiness checks and data-driven copy for Release Notes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from generators.parsing import parse_change_rows as _parse_change_rows
from generators.release_notes_report_tables import (
    build_analyze_report_rows,
    build_custom_client_report_tables,
    parse_analyze_report_rows,
    parse_custom_client_report_tables,
)
from generators.release_notes_summary_tables import build_highlight_summary

InsightLevel = Literal["blocker", "warning", "suggestion", "ok"]

_GENERIC_SUMMARY = re.compile(
    r"^this release includes .*(reporting enhancements|documentation updates|semantic model)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReleaseInsight:
    level: InsightLevel
    message: str
    action: str = ""


@dataclass
class ReadinessReport:
    ready: bool = False
    score: int = 0
    score_label: str = "Needs work"
    score_breakdown: dict[str, int] = field(default_factory=dict)
    insights: list[ReleaseInsight] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def blockers(self) -> list[ReleaseInsight]:
        return [item for item in self.insights if item.level == "blocker"]

    @property
    def warnings(self) -> list[ReleaseInsight]:
        return [item for item in self.insights if item.level == "warning"]

    @property
    def suggestions(self) -> list[ReleaseInsight]:
        return [item for item in self.insights if item.level == "suggestion"]


def is_generic_release_summary(text: str) -> bool:
    """True when summary text is legacy boilerplate rather than ticket-driven."""
    return bool(_GENERIC_SUMMARY.match((text or "").strip()))


def build_release_summary_paragraph(extracted: list[dict[str, Any]]) -> str:
    """One concise Release Summary paragraph derived from ticket/report inventory."""
    if not extracted:
        return (
            "This release includes reporting enhancements, custom client updates, "
            "and semantic model improvements."
        )

    from generators.release_notes_quality import build_key_highlight_lines

    highlights = build_key_highlight_lines(extracted)
    if highlights:
        lines = [line.strip() for line in highlights[:5] if line.strip()]
        if len(lines) == 1:
            return f"This release delivers {lines[0]}."
        if len(lines) == 2:
            return f"This release delivers {lines[0]} and {lines[1]}."
        if len(lines) > 2:
            return f"This release delivers {', '.join(lines[:-1])}, and {lines[-1]}."

    summary = build_highlight_summary(extracted)
    pieces: list[str] = []

    asset_bits: list[str] = []
    dash_total = summary.analyze.dashboards + summary.custom.dashboards
    pag_total = summary.analyze.paginated + summary.custom.paginated
    if dash_total:
        asset_bits.append(f"{dash_total} dashboard{'s' if dash_total != 1 else ''}")
    if pag_total:
        asset_bits.append(f"{pag_total} paginated report{'s' if pag_total != 1 else ''}")
    if asset_bits:
        pieces.append(" and ".join(asset_bits))

    scope_bits: list[str] = []
    if summary.analyze.tickets:
        scope_bits.append(f"{summary.analyze.tickets} Analyze (Standard) ticket(s)")
    if summary.custom.tickets:
        clients = ", ".join(sorted(summary.custom_by_client, key=str.lower))
        scope_bits.append(f"{summary.custom.tickets} custom ticket(s) ({clients})")
    if scope_bits:
        pieces.append("; ".join(scope_bits))

    if not pieces:
        return "This release includes reporting and semantic model updates."

    return f"This release delivers {pieces[0]}" + (
        f" across {pieces[1]}." if len(pieces) > 1 else "."
    )


def assess_release_notes_readiness(data: dict[str, Any]) -> ReadinessReport:
    """Evaluate whether the draft is complete enough to publish without rework."""
    extracted = data.get("extracted") or []
    change_rows = _parse_change_rows(data.get("change_rows", ""))
    analyze_rows = parse_analyze_report_rows(data.get("analyze_report_rows", ""))
    custom_tables = parse_custom_client_report_tables(data.get("custom_report_tables", ""))
    insights: list[ReleaseInsight] = []

    ticket_keys = {
        str(entry.get("ticket") or "").strip().upper()
        for entry in extracted
        if str(entry.get("ticket") or "").strip()
    }
    for row in change_rows:
        ticket = (row[0] or "").strip().upper() if row else ""
        if ticket and "-" in ticket:
            ticket_keys.add(ticket)

    if extracted:
        built_analyze = build_analyze_report_rows(extracted)
        built_custom = build_custom_client_report_tables(extracted)
    else:
        built_analyze = []
        built_custom = {}

    summary = build_highlight_summary(extracted) if extracted else None

    stats: dict[str, Any] = {
        "total_tickets": len(ticket_keys) or len(change_rows),
        "analyze_tickets": summary.analyze.tickets if summary else 0,
        "custom_tickets": summary.custom.tickets if summary else 0,
        "dashboards": (
            (summary.analyze.dashboards + summary.custom.dashboards) if summary else 0
        ),
        "paginated": (
            (summary.analyze.paginated + summary.custom.paginated) if summary else 0
        ),
        "custom_clients": sorted(
            (custom_tables or built_custom).keys(),
            key=str.lower,
        ),
    }

    if not ticket_keys and not change_rows:
        insights.append(
            ReleaseInsight(
                "blocker",
                "No tickets in this draft — select tickets in Step 2 first.",
                "Go back to Step 2 and lock release tickets.",
            )
        )

    if data.get("include_fix_version_metadata", True) and not (data.get("version") or "").strip():
        insights.append(
            ReleaseInsight(
                "blocker",
                "Release version is empty.",
                "Select a fix version on Step 1, or set version on Step 3.",
            )
        )

    if not change_rows and ticket_keys:
        insights.append(
            ReleaseInsight(
                "blocker",
                "Ticket Details table is empty but tickets are selected.",
                "Click **Rebuild Ticket Details** on Step 3.",
            )
        )

    if change_rows and not ticket_keys:
        def _row_test_by(row: list[str]) -> str:
            if len(row) >= 5:
                return (row[3] or "").strip()
            if len(row) >= 3:
                return (row[2] or "").strip()
            return ""

        missing_test_by = sum(1 for row in change_rows if not _row_test_by(row))
        if missing_test_by:
            insights.append(
                ReleaseInsight(
                    "warning",
                    f"{missing_test_by} Ticket Details row(s) missing **Test**.",
                    "Rebuild Ticket Details to assign QA names.",
                )
            )

    inventory_rows = list(analyze_rows) or [row.to_row() for row in built_analyze]
    for client_rows in (custom_tables or {k: [r.to_row() for r in v] for k, v in built_custom.items()}).values():
        inventory_rows.extend(client_rows)

    # For 6-col: ticket at index 2; for 5-col detail: ticket at index 1
    missing_owner = 0
    for row in inventory_rows:
        if len(row) >= 6 and not (row[3] or "").strip():
            missing_owner += 1
        elif len(row) == 5 and not (row[2] or "").strip():
            missing_owner += 1

    if missing_owner:
        insights.append(
            ReleaseInsight(
                "warning",
                f"{missing_owner} report row(s) missing **Owner** (Jira assignee).",
                "Ensure tickets have assignees in Jira, then rebuild inventory tables.",
            )
        )

    summary_p1 = (data.get("summary_p1") or "").strip()
    if summary_p1 and _GENERIC_SUMMARY.match(summary_p1):
        suggested = build_release_summary_paragraph(extracted) if extracted else ""
        insights.append(
            ReleaseInsight(
                "suggestion",
                "Release Summary still uses generic boilerplate text.",
                f"Use the data-driven line: “{suggested}”" if suggested else "Rewrite to match this release.",
            )
        )

    deploy_lines = [
        line.strip()
        for line in (data.get("deployment_rows") or "").splitlines()
        if line.strip()
    ]
    empty_deploy_status = sum(
        1 for line in deploy_lines if len(line.split("|")) >= 3 and not line.split("|")[2].strip()
    )
    if deploy_lines and empty_deploy_status == len(deploy_lines):
        insights.append(
            ReleaseInsight(
                "suggestion",
                "Deployment tracking rows have no Status or Deployment ID yet.",
                "Use **Fill from Deployer / History** after deploy, or paste deployment output.",
            )
        )

    evidence_raw = (
        data.get("testing_evidence_tickets")
        or data.get("screenshot_names")
        or data.get("screenshot_tickets")
        or ""
    )
    evidence_lines = [line.strip() for line in evidence_raw.splitlines() if line.strip()]
    evidence_ticket_keys = {
        line.split()[0].strip().upper()
        for line in evidence_lines
        if "-" in line and not line.lower().startswith("add ")
    }
    if ticket_keys and not evidence_lines:
        insights.append(
            ReleaseInsight(
                "suggestion",
                "Testing Evidence section has no ticket keys.",
                "Rebuild highlights — ticket keys auto-populate for testers.",
            )
        )
    elif ticket_keys and evidence_lines and not evidence_ticket_keys:
        insights.append(
            ReleaseInsight(
                "suggestion",
                "Testing Evidence text is present but no ticket keys were detected.",
                "Use **Rebuild Highlights & Dashboards** on Step 3 to refresh the ticket list.",
            )
        )

    if summary and summary.total_tickets and not analyze_rows and not built_analyze and summary.analyze.tickets:
        insights.append(
            ReleaseInsight(
                "warning",
                "Analyze tickets exist but the Analyze inventory table is empty.",
                "Click **Rebuild Highlights & Dashboards**.",
            )
        )

    if ticket_keys and not (data.get("release_owner") or "").strip():
        insights.append(
            ReleaseInsight(
                "warning",
                "Release Owner is empty.",
                "Fill Release Owner on Step 3 before publishing.",
            )
        )

    if ticket_keys and not (data.get("dev_team") or "").strip():
        insights.append(
            ReleaseInsight(
                "suggestion",
                "Dev Team field is empty.",
                "Add the dev team name on Step 3 metadata.",
            )
        )

    if not insights:
        insights.append(
            ReleaseInsight(
                "ok",
                "Structure looks complete — summary tables, delivered reports, Ticket Details, and post-deploy sections are populated.",
            )
        )

    blockers = [item for item in insights if item.level == "blocker"]
    warnings = [item for item in insights if item.level == "warning"]
    ready = not blockers

    score, score_breakdown = _compute_readiness_score(insights)
    if ready and not warnings and score >= 95:
        score_label = "Ready to publish"
    elif ready and score >= 80:
        score_label = "Ready with minor warnings"
    elif ready:
        score_label = "Publishable — review warnings"
    else:
        score_label = "Fix blockers before publishing"

    return ReadinessReport(
        ready=ready,
        score=score,
        score_label=score_label,
        score_breakdown=score_breakdown,
        insights=insights,
        stats=stats,
    )


def _compute_readiness_score(insights: list[ReleaseInsight]) -> tuple[int, dict[str, int]]:
    """Return 0–100 score and per-level deduction counts."""
    score = 100
    breakdown: dict[str, int] = {"blockers": 0, "warnings": 0, "suggestions": 0}
    for item in insights:
        if item.level == "blocker":
            score -= 40
            breakdown["blockers"] += 1
        elif item.level == "warning":
            score -= 10
            breakdown["warnings"] += 1
        elif item.level == "suggestion":
            score -= 2
            breakdown["suggestions"] += 1
    return max(0, min(100, score)), breakdown


def readiness_to_dict(report: ReadinessReport) -> dict[str, Any]:
    """JSON-serializable readiness payload for UI and MCP."""
    return {
        "ready": report.ready,
        "score": report.score,
        "score_label": report.score_label,
        "score_breakdown": dict(report.score_breakdown),
        "blockers": [{"message": i.message, "action": i.action} for i in report.blockers],
        "warnings": [{"message": i.message, "action": i.action} for i in report.warnings],
        "suggestions": [{"message": i.message, "action": i.action} for i in report.suggestions],
        "stats": dict(report.stats),
    }


def readiness_data_from_session(ss: dict[str, Any]) -> dict[str, Any]:
    """Map Streamlit session state to the readiness assessor input dict."""
    return {
        "version": ss.get("rn_version", ""),
        "release_date": ss.get("rn_date", ""),
        "dev_team": ss.get("rn_dev_team", ""),
        "release_owner": ss.get("rn_release_owner", ""),
        "extracted": ss.get("rn_extracted", []),
        "summary_p1": ss.get("rn_summary_p1", ""),
        "change_rows": ss.get("rn_change_rows", ""),
        "analyze_report_rows": ss.get("rn_analyze_report_rows", ""),
        "custom_report_tables": ss.get("rn_custom_report_tables", ""),
        "deployment_rows": ss.get("rn_deployment_rows", ""),
        "sanity_checklist": ss.get("rn_sanity_checklist", ""),
        "testing_evidence_tickets": ss.get("rn_testing_evidence_tickets", ss.get("rn_screenshot_names", "")),
        "screenshot_names": ss.get("rn_testing_evidence_tickets", ss.get("rn_screenshot_names", "")),
        "excluded_tickets": ss.get("rn_excluded_tickets", ""),
    }
