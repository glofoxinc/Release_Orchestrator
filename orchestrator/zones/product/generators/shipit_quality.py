"""SHIPIT draft quality assessment — CAB readiness checklist."""

from __future__ import annotations

from typing import Any

_GOLD_SECTIONS = (
    "What is changing, in business terms",
    "Who is affected",
    "Not included in this change",
    "How it is deployed",
    "Supporting records",
)

_PLAN_MARKERS = {
    "implementation_plan": ("Pre-deployment backups", "Do not change Production RLS"),
    "verification_plan": ("1.", "Roll back"),
    "rollback_plan": ("pre-deployment backup", "No RLS"),
    "business_impact": ("Before:", "After:", "Ticket:"),
    "communication_plan": ("Pre-deployment", "After rollback"),
    "risks_management": ("Overall", "Do not describe residual risk as low"),
    "qa_test_plan": ("Performance testing",),
}


def assess_shipit_draft(
    ctx: dict[str, Any],
    *,
    summary: str = "",
    description_plain: str = "",
    plans: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Score a SHIPIT draft against gold-standard patterns (17036 / 17191)."""
    extracted = ctx.get("extracted") or []
    plans = plans or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    if summary:
        add(
            "Summary format",
            "Glofox Insights Customize BI - Prod Deployment" in summary
            and "Release Version" in summary,
            summary[:120],
        )

    for section in _GOLD_SECTIONS:
        add(
            f"Description section: {section}",
            section.lower() in description_plain.lower(),
        )

    if extracted:
        enriched = sum(1 for e in extracted if isinstance(e.get("evidence"), dict) and e["evidence"])
        add(
            "Jira evidence enrichment",
            enriched == len(extracted),
            f"{enriched}/{len(extracted)} tickets have parsed evidence",
        )
        for entry in extracted:
            key = str(entry.get("ticket") or "?")
            ev = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
            has_qa = bool(ev.get("qa_validator") or ev.get("stakeholder_approval"))
            add(
                f"Ticket {key}: QA or approval signal",
                has_qa or bool(entry.get("assignee")),
                "validator/stakeholder from Jira" if has_qa else "assignee fallback only",
            )

    for field, markers in _PLAN_MARKERS.items():
        text = str(plans.get(field) or "").strip()
        add(
            f"Plan field: {field}",
            bool(text) and all(m.lower() in text.lower() for m in markers[:2 if field == "business_impact" else 1]),
            f"{len(text)} chars" if text else "empty",
        )

    passed = sum(1 for c in checks if c["ok"])
    total = len(checks) or 1
    return {
        "passed": passed,
        "total": total,
        "score_pct": round(100 * passed / total),
        "ready_for_cab": passed >= max(total - 2, int(total * 0.9)),
        "checks": checks,
    }
