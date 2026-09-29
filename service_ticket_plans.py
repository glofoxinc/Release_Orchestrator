"""Pure plan builders for Service Ticket (SHIPIT / legacy TCKT) plans.

Shared by the Streamlit UI and headless Release Orchestrator callers. No Streamlit imports.

Default content follows SHIPIT-17036 evidence-based standard (Sushma / Customize BI).
"""

from __future__ import annotations

from collections import OrderedDict

from consolidation import deduplicate_by_dashboard
from template_engine import render_template


def consolidate_by_report(tickets: list[dict]) -> list[dict]:
    """Group tickets by dashboard/report label for plan templates."""
    groups: OrderedDict[str, dict] = OrderedDict()
    for e in tickets:
        if e["type"] == "Custom":
            label = f"{e['client']} - {e['report']}" if e["report"] else e["client"]
        else:
            label = e["report"] or e["description"]

        if label not in groups:
            groups[label] = {"label": label, "descs": [], "tickets": []}
        desc = e.get("description", "")
        if desc and desc.lower() != label.lower():
            groups[label]["descs"].append(desc.lower())
        groups[label]["tickets"].append(e["ticket"])

    result = []
    for g in groups.values():
        unique_descs = list(dict.fromkeys(g["descs"]))
        summary = ", ".join(unique_descs) if unique_descs else ""
        refs = ", ".join(g["tickets"])
        result.append({"label": g["label"], "summary": summary, "refs": refs})
    # Safety-net against duplicate dashboards leaking through.
    return deduplicate_by_dashboard(result)


def build_impl(ctx: dict) -> str:
    from generators.shipit_evidence_plans import build_evidence_implementation
    return build_evidence_implementation(ctx)


def build_test(ctx: dict) -> str:
    from generators.shipit_evidence_plans import build_evidence_verification
    return build_evidence_verification(ctx)


def build_backout(ctx: dict) -> str:
    from generators.shipit_evidence_plans import build_evidence_rollback
    return build_evidence_rollback(ctx)


def build_impact(ctx: dict) -> str:
    from generators.shipit_evidence_plans import build_evidence_business_impact
    return build_evidence_business_impact(ctx)


def build_communication(ctx: dict) -> str:
    from generators.shipit_evidence_plans import build_evidence_communication
    return build_evidence_communication(ctx)


def build_risks(ctx: dict) -> str:
    from generators.shipit_evidence_plans import build_evidence_risks
    return build_evidence_risks(ctx)


def build_qa_test_plan(ctx: dict) -> str:
    from generators.shipit_evidence_plans import build_qa_evidence_test_plan
    return build_qa_evidence_test_plan(ctx)


def build_reason(ctx: dict) -> str:
    return "Production Deployment"


def _ticket_refs(ctx: dict) -> str:
    refs = [
        str(entry.get("ticket") or "").strip()
        for entry in ctx.get("extracted") or []
        if str(entry.get("ticket") or "").strip()
    ]
    return ", ".join(dict.fromkeys(refs)) or "the release tickets"


# Private aliases matching the historical UI module names.
_consolidate_by_report = consolidate_by_report
_build_impl = build_impl
_build_test = build_test
_build_backout = build_backout
_build_impact = build_impact
_build_communication = build_communication
_build_reason = build_reason
