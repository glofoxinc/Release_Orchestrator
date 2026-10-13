"""Parse Jira ticket summaries into clear report names and artifact types."""

from __future__ import annotations

import re
from typing import Literal

AssetType = Literal["Dashboard", "Paginated report", "Semantic model", "Documentation", ""]

_TITLE_SEP = re.compile(r"\s*[-–—]\s*")

_ACTION_LEAD = re.compile(
    r"^(?:add|fix|update|enhance|change|remove|create|implement|standardize|"
    r"correct|improve|align|migrate|rebuild|refactor|document|deploy)\b",
    re.IGNORECASE,
)
_PAGINATED = re.compile(r"\bpaginated\s*report\b|\bpaginated\b", re.IGNORECASE)
_DASHBOARD = re.compile(r"\bdashboard\b", re.IGNORECASE)
_SEMANTIC = re.compile(r"\bsemantic\s*model\b", re.IGNORECASE)
_DOCUMENTATION = re.compile(r"\bdocumentation\b|\bdoc\s*page\b|\bmeasures\s+and\s+definitions\b", re.IGNORECASE)

_VAGUE_REPORT = re.compile(
    r"^(?:insights?|analytics|analyze|standard|reporting|bi|glofox|ignite|"
    r"customize\s*bi|n/?a|tbd)$",
    re.IGNORECASE,
)

_STRIP_PAGINATED_SUFFIX = re.compile(
    r"\s*\(?\s*paginated\s*report\s*\)?\s*$",
    re.IGNORECASE,
)
_STRIP_DASHBOARD_SUFFIX = re.compile(r"\s+dashboard\s*$", re.IGNORECASE)
_STRIP_PARENS = re.compile(r"\s*\([^)]*\)\s*$")
_WORK_DETAIL = re.compile(
    r"\b(?:needed|fix|issue|bug|reconfig\w*|update|enhancement|change|minor|major)\b",
    re.IGNORECASE,
)


def _segments(summary: str) -> list[str]:
    return [part.strip() for part in _TITLE_SEP.split(summary or "") if part.strip()]


def detect_asset_type(text: str) -> AssetType:
    blob = text or ""
    if _PAGINATED.search(blob):
        return "Paginated report"
    if _SEMANTIC.search(blob):
        return "Semantic model"
    if _DOCUMENTATION.search(blob):
        return "Documentation"
    if _DASHBOARD.search(blob):
        return "Dashboard"
    return ""


def _strip_artifact_words(label: str) -> str:
    out = (label or "").strip()
    out = _STRIP_PAGINATED_SUFFIX.sub("", out).strip()
    out = _STRIP_DASHBOARD_SUFFIX.sub("", out).strip()
    out = _STRIP_PARENS.sub("", out).strip()
    return out


def _is_action_segment(segment: str) -> bool:
    return bool(_ACTION_LEAD.match(segment.strip()))


def _score_name_segment(segment: str) -> int:
    cleaned = _strip_artifact_words(segment)
    if not cleaned or _VAGUE_REPORT.match(cleaned):
        return -10
    if _is_action_segment(cleaned):
        return -5
    if detect_asset_type(segment) and cleaned.lower() in {
        "paginated report",
        "dashboard",
        "semantic model",
    }:
        return -8
    score = min(len(cleaned), 40)
    if _PAGINATED.search(segment) or _DASHBOARD.search(segment):
        score += 5
    return score


def _merge_paginated_title(segments: list[str]) -> tuple[str, AssetType]:
    """Visit Analysis - Member Details paginated report → Visit Analysis Member Details."""
    asset: AssetType = "Paginated report"
    if len(segments) >= 2 and _PAGINATED.search(segments[-1]):
        parent = _strip_artifact_words(segments[-2])
        detail = _strip_artifact_words(segments[-1])
        if parent and detail and parent.lower() not in detail.lower():
            return f"{parent} {detail}", asset
        if detail:
            return detail, asset
    for seg in reversed(segments):
        if _PAGINATED.search(seg):
            return _strip_artifact_words(seg) or seg, asset
    return "", asset


def _pick_report_name(segments: list[str], *, fallback: str) -> str:
    if not segments:
        return _strip_artifact_words(fallback) or fallback

    if len(segments) == 2:
        left, right = segments[0], segments[1]
        if (
            not _is_action_segment(left)
            and not _VAGUE_REPORT.match(_strip_artifact_words(left))
            and _WORK_DETAIL.search(right)
            and not detect_asset_type(right)
        ):
            return _strip_artifact_words(left) or left

    asset = detect_asset_type(" ".join(segments))
    if asset == "Paginated report":
        merged, _ = _merge_paginated_title(segments)
        if merged:
            return merged

    candidates: list[tuple[int, str]] = []
    for seg in segments:
        cleaned = _strip_artifact_words(seg)
        if not cleaned:
            continue
        candidates.append((_score_name_segment(seg), cleaned))

    if not candidates:
        return _strip_artifact_words(fallback) or fallback

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_name = candidates[0]

    # Vague winner (e.g. "Insights") — prefer next segment that names a dashboard/report.
    if _VAGUE_REPORT.match(best_name) and len(candidates) > 1:
        for score, name in candidates[1:]:
            if score > 0 and not _VAGUE_REPORT.match(name):
                return name

    if best_score > 0:
        return best_name
    return _strip_artifact_words(fallback) or fallback


def _pick_description(segments: list[str], report: str, fallback: str) -> str:
    for seg in segments:
        if _is_action_segment(seg):
            return seg.strip()
    for seg in reversed(segments):
        cleaned = seg.strip()
        if cleaned.lower() == report.lower():
            continue
        if detect_asset_type(seg) and _strip_artifact_words(seg).lower() == report.lower():
            continue
        if _strip_artifact_words(seg).lower() != report.lower():
            return cleaned
    return fallback if fallback.lower() != report.lower() else report


def format_report_display_name(report: str, asset_type: AssetType) -> str:
    """Release notes Dashboard/Report column: ``Name (Paginated report)`` when helpful."""
    base = _strip_artifact_words(report)
    if not base:
        return report
    if not asset_type:
        return base
    low = base.lower()
    if asset_type == "Paginated report" and _PAGINATED.search(base):
        return base
    if asset_type == "Dashboard" and _DASHBOARD.search(base):
        return base
    return f"{base} ({asset_type})"


def refine_ticket_title_fields(
    summary: str,
    *,
    report: str,
    description: str,
) -> dict[str, str]:
    """Return improved report, description, asset_type, and display_report from the Jira title."""
    segments = _segments(summary)
    combined = " ".join(segments) if segments else summary
    asset_type = detect_asset_type(combined) or detect_asset_type(description)

    improved_report = _pick_report_name(segments, fallback=report or summary)
    if _VAGUE_REPORT.match(_strip_artifact_words(report)) and improved_report:
        report = improved_report
    elif improved_report and (_VAGUE_REPORT.match(_strip_artifact_words(report)) or len(report) < len(improved_report)):
        report = improved_report
    else:
        report = _strip_artifact_words(report) or improved_report

    if not asset_type:
        asset_type = detect_asset_type(report) or detect_asset_type(description)

    description = _pick_description(segments, report, description)
    display_report = format_report_display_name(report, asset_type)

    return {
        "report": report,
        "description": description,
        "asset_type": asset_type,
        "display_report": display_report,
    }


__all__ = [
    "detect_asset_type",
    "format_report_display_name",
    "refine_ticket_title_fields",
]
