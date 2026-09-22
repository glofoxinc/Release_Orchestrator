"""Load and learn from real deployment change tickets in Jira (legacy TCKT + SHIPIT).

Reference tickets such as TCKT-111137 / SHIPIT-8346 define the canonical structure for
summaries, descriptions, plans, approvers, and approver groups.

Active workspace config targets SHIPIT — see ``shipit_reference.py``. This module
remains for rollback reference and historical TCKT templates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

import adf_builder as adf
import config
import jira_client
from diff_engine import extract_ticket_fields

_DEPLOYMENT_JQL = (
    '(project = SHIPIT OR project = TCKT) AND summary ~ "Production Deployment" '
    'AND summary ~ "Insights Customize BI" ORDER BY created DESC'
)


def _select_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or value.get("name") or "")
    return str(value or "")


def _adf_plain(value: Any) -> str:
    if isinstance(value, dict) and value.get("type") == "doc":
        return adf.adf_to_plain_text(value)
    if isinstance(value, str):
        return value
    return ""


def _parse_planned_datetime(raw: str | None) -> tuple[date | None, time | None]:
    if not raw:
        return None, None
    cleaned = raw.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.date(), dt.time().replace(microsecond=0)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(cleaned)
        return dt.date(), dt.time().replace(microsecond=0)
    except ValueError:
        return None, None


def _normalize_approvers(raw: Any) -> list[dict[str, str]]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        account_id = str(item.get("accountId") or item.get("account_id") or "")
        if account_id:
            out.append({"accountId": account_id})
    return out


def _normalize_groups(raw: Any) -> list[dict[str, str]]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("name") or "")
        else:
            name = str(item)
        if name:
            out.append({"name": name})
    return out


@dataclass
class TcktReference:
    """Canonical payload extracted from a live Jira TCKT."""

    key: str
    summary: str = ""
    description_plain: str = ""
    description_adf: dict = field(default_factory=dict)
    implementation_plan: str = ""
    test_plan: str = ""
    backout_plan: str = ""
    business_impact: str = ""
    communication_plan: str = ""
    reason_for_change: str = ""
    risks_management: str = ""
    qa_test_plan: str = ""
    change_type: str = "Normal"
    change_risk: str = "Medium"
    impact: str = "Moderate / Limited"
    urgency: str = "Medium"
    approvers: list[dict[str, str]] = field(default_factory=list)
    approver_groups: list[dict[str, str]] = field(default_factory=list)
    planned_start_date: date | None = None
    planned_start_time: time | None = None
    planned_end_date: date | None = None
    planned_end_time: time | None = None
    schedule_timezone: str = ""
    created: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "summary": self.summary,
            "description_plain": self.description_plain,
            "change_type": self.change_type,
            "change_risk": self.change_risk,
            "impact": self.impact,
            "urgency": self.urgency,
            "approvers": list(self.approvers),
            "approver_groups": list(self.approver_groups),
        }


def _timezone_name_from_iso(raw: str | None) -> str | None:
    """Map planned start/end ISO offset to an IANA zone (e.g. SHIPIT-16769 uses -0500 → Chicago)."""
    if not raw:
        return None
    cleaned = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    offset_min = int(dt.utcoffset().total_seconds() // 60) if dt.utcoffset() else 0
    # Common deployment zones by fixed offset (DST handled when re-submitting via zone name).
    offset_zone_map = {
        -300: "America/Chicago",
        -360: "America/Chicago",
        -240: "America/New_York",
        -420: "America/Denver",
        330: "Asia/Kolkata",
        0: "UTC",
        60: "Europe/Dublin",
    }
    return offset_zone_map.get(offset_min)


def fetch_reference(issue_key: str) -> TcktReference:
    """Load one TCKT and extract fields used by the Service Ticket wizard."""
    issue = jira_client.get_issue(issue_key.strip().upper())
    fields = extract_ticket_fields(issue)
    raw_fields = issue.get("fields", {}) or {}

    desc_adf = fields.get("description") or adf.doc(adf.paragraph(adf.text(" ")))
    if not isinstance(desc_adf, dict):
        desc_adf = adf.doc(adf.paragraph(adf.text(str(desc_adf))))

    start_d, start_t = _parse_planned_datetime(fields.get("planned_start"))
    end_d, end_t = _parse_planned_datetime(fields.get("planned_end"))
    sched_tz = (
        _timezone_name_from_iso(fields.get("planned_start"))
        or _timezone_name_from_iso(fields.get("planned_end"))
        or ""
    )

    return TcktReference(
        key=issue.get("key", issue_key),
        summary=str(fields.get("summary") or ""),
        description_plain=_adf_plain(desc_adf),
        description_adf=desc_adf,
        implementation_plan=_adf_plain(fields.get("implementation_plan")),
        test_plan=_adf_plain(fields.get("test_plan")),
        backout_plan=_adf_plain(fields.get("backout_plan")),
        business_impact=_adf_plain(fields.get("business_impact")),
        communication_plan=_adf_plain(fields.get("communication_plan")),
        reason_for_change=str(fields.get("reason_for_change") or ""),
        risks_management=_adf_plain(fields.get("risks_management")),
        qa_test_plan=_adf_plain(fields.get("qa_test_plan")),
        change_type=_select_label(fields.get("change_type")) or "Normal",
        change_risk=_select_label(fields.get("change_risk")) or "Medium",
        impact=_select_label(fields.get("impact")) or "Moderate / Limited",
        urgency=_select_label(fields.get("urgency")) or "Medium",
        approvers=_normalize_approvers(fields.get("approvers")),
        approver_groups=_normalize_groups(fields.get("approver_groups")),
        planned_start_date=start_d,
        planned_start_time=start_t,
        planned_end_date=end_d,
        planned_end_time=end_t,
        schedule_timezone=sched_tz,
        created=str(raw_fields.get("created") or ""),
    )


def search_deployment_tickets(
    *,
    max_results: int = 30,
    jql_extra: str = "",
) -> list[dict[str, Any]]:
    """Return recent Customize BI production-deployment change tickets (SHIPIT + legacy TCKT)."""
    jql = _DEPLOYMENT_JQL
    if jql_extra:
        jql = f"{jql[:-len(' ORDER BY created DESC')]} AND {jql_extra} ORDER BY created DESC"
    fields = [
        "summary",
        "status",
        "created",
        "updated",
        "priority",
        config.TCKT_FIELDS.get("approvers", ""),
        config.TCKT_FIELDS.get("approver_groups", ""),
    ]
    fields = [f for f in fields if f]
    return jira_client.search_issues_jql(jql, fields=fields, max_results=max_results)


def learn_from_tickets(tickets: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate common approvers/groups from historical deployment TCKTs."""
    from collections import Counter

    approver_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    cf_approvers = config.TCKT_FIELDS.get("approvers", "")
    cf_groups = config.TCKT_FIELDS.get("approver_groups", "")

    for ticket in tickets:
        f = ticket.get("fields", {}) or {}
        for item in _normalize_approvers(f.get(cf_approvers)):
            approver_counts[item["accountId"]] += 1
        for item in _normalize_groups(f.get(cf_groups)):
            group_counts[item["name"]] += 1

    return {
        "approver_account_ids": [aid for aid, _ in approver_counts.most_common(8)],
        "approver_groups": [name for name, _ in group_counts.most_common(6)],
        "sample_count": len(tickets),
    }


def derive_client_label(extracted: list[dict]) -> str:
    """Client hint for summary line (e.g. Glofox, Multi-Client)."""
    clients = [
        e["client"]
        for e in extracted
        if e.get("type") == "Custom" and e.get("client") not in ("Unknown", "Standard")
    ]
    if not clients:
        return "Report Updates"
    unique = sorted(set(clients))
    if len(unique) == 1:
        return unique[0]
    if len(unique) <= 3:
        return " / ".join(unique)
    return "Multi-Client"


def build_summary_from_reference_pattern(
    *,
    version_name: str,
    extracted: list[dict],
    team: str | None = None,
    environment: str | None = None,
) -> str:
    """Match TCKT-111137 style: Production Deployment – Team - Client - Report Updates (v…)."""
    env = environment or config.DEPLOY_ENVIRONMENT
    team_name = team or config.TCKT_SUMMARY_TEAM or config.WORKSPACE_NAME
    client = derive_client_label(extracted)
    if client == "Report Updates":
        return f"{env} Deployment \u2013 {team_name} - Report Updates ({version_name})"
    return f"{env} Deployment \u2013 {team_name} - {client} - Report Updates ({version_name})"


_VERSION_RE = re.compile(r"\(v[\d.]+\)")


def apply_reference_to_session(ref: TcktReference, ss: dict, *, include_summary: bool = False) -> None:
    """Copy reference ticket content into Streamlit session state."""
    ss["stk_reference_key"] = ref.key
    if include_summary and ref.summary:
        ss["stk_summary"] = ref.summary

    ss["stk_description_custom"] = True
    ss["stk_description_text"] = ref.description_plain
    ss["stk_description_adf"] = ref.description_adf

    if ref.implementation_plan:
        ss["stk_impl_plan"] = ref.implementation_plan
    if ref.test_plan:
        ss["stk_test_plan"] = ref.test_plan
    if ref.backout_plan:
        ss["stk_backout_plan"] = ref.backout_plan
    if ref.business_impact:
        ss["stk_business_impact"] = ref.business_impact
    if ref.communication_plan:
        ss["stk_communication_plan"] = ref.communication_plan
    if ref.reason_for_change:
        ss["stk_reason_for_change"] = ref.reason_for_change
    if ref.risks_management:
        ss["stk_risks_management"] = ref.risks_management
    if ref.qa_test_plan:
        ss["stk_qa_test_plan"] = ref.qa_test_plan

    ss["stk_change_type"] = ref.change_type
    ss["stk_change_risk"] = ref.change_risk
    ss["stk_impact"] = ref.impact
    ss["stk_urgency"] = ref.urgency

    if ref.approvers:
        ss["stk_approvers"] = list(ref.approvers)
    if ref.approver_groups:
        ss["stk_approver_groups"] = list(ref.approver_groups)

    if ref.planned_start_date:
        ss["stk_planned_start_date"] = ref.planned_start_date
    if ref.planned_start_time:
        ss["stk_planned_start_time"] = ref.planned_start_time
    if ref.planned_end_date:
        ss["stk_planned_end_date"] = ref.planned_end_date
    if ref.planned_end_time:
        ss["stk_planned_end_time"] = ref.planned_end_time
    if ref.schedule_timezone:
        ss["stk_schedule_tz"] = ref.schedule_timezone

    ss.pop("stk_approver_validation", None)


def apply_learned_defaults(ss: dict, learned: dict[str, Any]) -> None:
    """Seed approvers/groups from historical deployment tickets when unset."""
    if not ss.get("stk_approvers"):
        ss["stk_approvers"] = [
            {"accountId": aid} for aid in learned.get("approver_account_ids", [])
        ]
    if not ss.get("stk_approver_groups"):
        ss["stk_approver_groups"] = [
            {"name": name} for name in learned.get("approver_groups", [])
        ]
