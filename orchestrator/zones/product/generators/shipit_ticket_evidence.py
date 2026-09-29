"""Fetch and parse Jira ticket evidence for SHIPIT-17036-grade service tickets.

Pulls description + comments from each release ticket and extracts QA dates,
Product decisions, definition risks, numeric examples, and CAB exception flags.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

import adf_builder as adf
import jira_client

# ── Regex patterns (derived from SHIPIT-17036 / AN-5516) ─────────────────

_PERSON_NAME = r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4}"
_QA_VALIDATION = re.compile(
    rf"(?P<name>{_PERSON_NAME})\s+on\s+"
    r"(?P<date>\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})"
    r"[^.\n]*validated[^.\n]*",
    re.IGNORECASE,
)
_QA_VALIDATION_ALT = re.compile(
    rf"(?P<name>{_PERSON_NAME})\s+validated[^.\n]*"
    r"(?:on\s+)?(?P<date>\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})?",
    re.IGNORECASE,
)
_DASHBOARD_RULE = re.compile(
    r"one unique visit per calendar day|"
    r"glofox dashboard[^.]{0,80}one unique visit per calendar day",
    re.IGNORECASE,
)
_NUMERIC_EXAMPLE = re.compile(
    r"(?P<a>\d+)\s+event[- ]based[^.]{0,40}?(?:vs\.?|versus)\s*(?P<b>\d+)\s+"
    r"(?:distinct|unique|visit)",
    re.IGNORECASE,
)
_OPTION_GAP = re.compile(
    r"product has not (?:replied|posted|confirmed|answered)[^.]*option\s*[AB]",
    re.IGNORECASE,
)
_OPTION_DECISION = re.compile(
    r"(?:option\s*([AB])\b[^.]{0,120}(?:confirmed|proceeded|chosen|selected|accept)|"
    r"(?:confirmed|proceeded|chosen|selected|accept)[^.]{0,80}option\s*([AB])\b)",
    re.IGNORECASE,
)
_EXCEL_GAP = re.compile(
    r"excel[^.]{0,80}(?:not separately signed off|not signed off|was not separately)",
    re.IGNORECASE,
)
_PERF_GAP = re.compile(
    r"performance testing[^.]{0,40}(?:not performed|not documented|was not performed)",
    re.IGNORECASE,
)
_LOOKER_VALIDATION = re.compile(
    r"(?:data validation|validated?|validation)\s+(?:with|against)\s+looker|looker[^.\n]{0,60}(?:validation|validated)",
    re.IGNORECASE,
)
_QA_LOOKER_PAREN = re.compile(
    rf"(?P<name>{_PERSON_NAME})\s*\((?P<date>\d{{1,2}}\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\)"
    r"[^.\n]*(?:looker|data validation)",
    re.IGNORECASE,
)
_QA_WORKING_PAREN = re.compile(
    rf"(?P<name>{_PERSON_NAME})\s+confirmed\s+working as expected\s*"
    rf"\((?P<date>\d{{1,2}}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{{4}})\)",
    re.IGNORECASE,
)
_STAKEHOLDER_APPROVAL = re.compile(
    rf"(?P<name>{_PERSON_NAME})\s+approved\s+publish[^.\n]*"
    rf"(?:\((?P<date>\d{{1,2}}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{{4}})\))?",
    re.IGNORECASE,
)
_TEST_CASE = re.compile(r"(TC-\d{2}\s*[^.\n]+)", re.IGNORECASE)
_CUSTOM_WORKSPACE = re.compile(
    r"(customer-facing V2 Fitness BI workspace)",
    re.IGNORECASE,
)
_BEFORE_BLOCK = re.compile(
    r"Before:\s*(.+?)(?:\n\n|\nAfter:|\nAudience|$)",
    re.IGNORECASE | re.DOTALL,
)
_AFTER_BLOCK = re.compile(
    r"After:\s*(.+?)(?:\n\n|\nAudience|\nMeasured|$)",
    re.IGNORECASE | re.DOTALL,
)
_COLUMN_ADD = re.compile(
    r"(?:add(?:ed|ing)?|new)\s+(?:a\s+)?([A-Z][\w\s/-]{2,40}?)\s+column",
    re.IGNORECASE,
)
_AC_LINE = re.compile(r"^\s*(?:\d+[.)]\s*|-|\*)\s*(.+)$", re.MULTILINE)
_NOT_INCLUDED = re.compile(
    r"not included(?: in this change)?[:\s]*([\s\S]+?)(?:\n\n|how it is deployed|$)",
    re.IGNORECASE,
)


def _comment_plain(comments: list[dict]) -> str:
    parts: list[str] = []
    for comment in comments:
        body = comment.get("body")
        if isinstance(body, dict):
            text = adf.adf_to_plain_text(body).strip()
            if text:
                parts.append(text)
        elif isinstance(body, str) and body.strip():
            parts.append(body.strip())
    return "\n\n".join(parts)


def _first_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    return pattern.search(text or "")


def _bullet_lines(section: str) -> list[str]:
    lines: list[str] = []
    for raw in (section or "").splitlines():
        m = _AC_LINE.match(raw.strip())
        if m:
            line = m.group(1).strip()
            if line and len(line) > 3:
                lines.append(line)
    return lines


def parse_ticket_evidence(
    issue: dict[str, Any],
    comments: list[dict] | None = None,
) -> dict[str, Any]:
    """Parse SHIPIT-relevant evidence from a Jira issue + comments."""
    fields = issue.get("fields") or {}
    summary = str(fields.get("summary") or "").strip()
    desc_raw = fields.get("description")
    if isinstance(desc_raw, dict):
        description_plain = adf.adf_to_plain_text(desc_raw).strip()
    else:
        description_plain = str(desc_raw or "").strip()

    comment_plain = _comment_plain(comments or [])
    corpus = "\n".join(part for part in (summary, description_plain, comment_plain) if part)

    evidence: dict[str, Any] = {
        "summary": summary,
        "description_plain": description_plain,
        "comment_plain": comment_plain,
        "change_bullets": [],
        "not_included_bullets": [],
        "cab_exceptions": [],
    }

    # Change bullets from description (AC-style lines or first paragraphs)
    bullets = _bullet_lines(description_plain)
    if bullets:
        evidence["change_bullets"] = bullets[:8]
    elif description_plain:
        first_para = description_plain.split("\n\n")[0].strip()
        if first_para and len(first_para) > 20:
            evidence["change_bullets"] = [first_para[:500]]

    not_included_match = _NOT_INCLUDED.search(description_plain)
    if not_included_match:
        evidence["not_included_bullets"] = _bullet_lines(not_included_match.group(1))[:6]

    col_match = _first_match(_COLUMN_ADD, corpus)
    if col_match:
        evidence["artifact_column"] = col_match.group(1).strip()

    dash_match = _first_match(_DASHBOARD_RULE, corpus)
    if dash_match:
        evidence["dashboard_definition"] = "one unique visit per calendar day"

    num_match = _first_match(_NUMERIC_EXAMPLE, corpus)
    if num_match:
        evidence["numeric_example"] = (
            f"{num_match.group('a')} event-based visits vs "
            f"{num_match.group('b')} distinct visit days"
        )

    qa_corpus = comment_plain or corpus
    qa_match = (
        _first_match(_QA_VALIDATION, qa_corpus)
        or _first_match(_QA_VALIDATION_ALT, qa_corpus)
        or _first_match(_QA_VALIDATION, corpus)
        or _first_match(_QA_VALIDATION_ALT, corpus)
    )
    if qa_match:
        evidence["qa_validator"] = qa_match.group("name").strip()
        if qa_match.groupdict().get("date"):
            evidence["qa_date"] = qa_match.group("date").strip()
        evidence["qa_method"] = "validated against the Glofox dashboard"

    if "validated" in corpus.lower() and "glofox dashboard" in corpus.lower():
        evidence.setdefault("qa_method", "validated against the Glofox dashboard")

    if _first_match(_LOOKER_VALIDATION, corpus):
        evidence["looker_validation"] = True
        evidence["validation_source"] = "Looker"
        evidence.setdefault("qa_method", "verified and performed data validation with Looker")

    looker_qa = _first_match(_QA_LOOKER_PAREN, corpus) or _first_match(_QA_LOOKER_PAREN, comment_plain)
    if looker_qa:
        evidence["qa_validator"] = looker_qa.group("name").strip()
        evidence["qa_date"] = looker_qa.group("date").strip()
        evidence["looker_validation"] = True
        evidence["validation_source"] = "Looker"
        evidence["qa_method"] = "verified and performed data validation with Looker"

    working_qa = _first_match(_QA_WORKING_PAREN, corpus)
    if working_qa and not evidence.get("qa_validator"):
        evidence["qa_validator"] = working_qa.group("name").strip()
        evidence["qa_date"] = working_qa.group("date").strip()
        evidence.setdefault("qa_method", "confirmed working as expected")

    stakeholder = _first_match(_STAKEHOLDER_APPROVAL, corpus)
    if stakeholder:
        evidence["stakeholder_approval"] = {
            "name": stakeholder.group("name").strip(),
            "date": (stakeholder.groupdict().get("date") or "").strip(),
            "note": "approved publish to customer-facing",
        }

    test_cases = [m.group(1).strip() for m in _TEST_CASE.finditer(corpus)]
    if test_cases:
        evidence["test_cases"] = list(dict.fromkeys(test_cases))[:6]

    workspace_match = _first_match(_CUSTOM_WORKSPACE, corpus)
    if workspace_match:
        evidence["deploy_workspace"] = workspace_match.group(1)

    before_match = _first_match(_BEFORE_BLOCK, corpus)
    if before_match:
        evidence["before_state"] = " ".join(before_match.group(1).split())
    after_match = _first_match(_AFTER_BLOCK, corpus)
    if after_match:
        evidence["after_state"] = " ".join(after_match.group(1).split())

    if _first_match(_OPTION_GAP, corpus):
        evidence["product_decision_gap"] = (
            "Product has not replied to Option A vs Option B on the ticket"
        )
        evidence["cab_exceptions"].append(evidence["product_decision_gap"])

    opt_dec = _first_match(_OPTION_DECISION, corpus)
    if opt_dec:
        letter = (opt_dec.group(1) or opt_dec.group(2) or "").upper()
        evidence["product_decision"] = (
            f"Option {letter} (Glofox dashboard definition: one unique visit per calendar day)"
            if letter == "B"
            else f"Option {letter} confirmed on the ticket or in comments"
        )

    if _first_match(_EXCEL_GAP, corpus):
        evidence["excel_signoff_gap"] = True
        evidence["cab_exceptions"].append(
            "Excel export was requested and not separately signed off"
        )

    if _first_match(_PERF_GAP, corpus) or "performance testing: not performed" in corpus.lower():
        evidence["performance_testing_gap"] = True
        evidence["cab_exceptions"].append(
            "Performance testing was not performed/documented"
        )

    # Before / after heuristics from description
    if evidence.get("artifact_column") and not evidence.get("before_state"):
        col = evidence["artifact_column"]
        evidence["before_state"] = (
            f"The report does not include {col}. Operators cannot see the new metric on this extract."
        )
        evidence["after_state"] = (
            f"{col} appears on the same report. QA aligned the column to the Glofox dashboard "
            f"({evidence.get('dashboard_definition', 'ticket acceptance criteria')})."
        )

    if evidence.get("looker_validation") and not evidence.get("before_state"):
        evidence.setdefault(
            "before_state",
            "Class or filter behavior does not yet match Looker or the agreed acceptance criteria.",
        )
        evidence.setdefault(
            "after_state",
            "Filters or class logic match Looker-style variations validated in QA.",
        )

    if evidence.get("test_cases") and not evidence.get("before_state"):
        evidence.setdefault(
            "before_state",
            "Group/location filter behavior does not yet match the approved TC-01–03 scenarios.",
        )
        evidence.setdefault(
            "after_state",
            "Group-selected and no-group multi-location selections behave per ticket acceptance.",
        )

    return evidence


def _fetch_one(key: str) -> tuple[str, dict[str, Any] | None, str | None]:
    try:
        issue = jira_client.get_issue(key)
        comments = jira_client.get_issue_comments(key)
        return key, parse_ticket_evidence(issue, comments), None
    except Exception as exc:  # noqa: BLE001 — best-effort enrichment
        return key, None, str(exc)


def enrich_extracted_with_jira_evidence(
    extracted: list[dict],
    *,
    fetch_if_missing: bool = True,
) -> list[dict]:
    """Attach ``evidence`` dicts by fetching Jira description + comments."""
    if not extracted or not fetch_if_missing:
        return extracted

    keys_to_fetch: list[str] = []
    for entry in extracted:
        key = str(entry.get("ticket") or "").strip().upper()
        if key and not entry.get("evidence"):
            keys_to_fetch.append(key)

    if not keys_to_fetch:
        return extracted

    evidence_by_key: dict[str, dict[str, Any]] = {}
    errors_by_key: dict[str, str] = {}

    if len(keys_to_fetch) == 1:
        key, ev, err = _fetch_one(keys_to_fetch[0])
        if ev:
            evidence_by_key[key] = ev
        if err:
            errors_by_key[key] = err
    else:
        for key, ev, err in jira_client.readonly_map(_fetch_one, keys_to_fetch):
            if ev:
                evidence_by_key[key] = ev
            if err:
                errors_by_key[key] = err

    enriched: list[dict] = []
    for entry in extracted:
        copy = deepcopy(entry)
        key = str(copy.get("ticket") or "").strip().upper()
        if key in evidence_by_key:
            copy["evidence"] = evidence_by_key[key]
            ev = evidence_by_key[key]
            if ev.get("change_bullets") and len(str(copy.get("description") or "")) < 30:
                copy["description"] = ev["change_bullets"][0]
        if key in errors_by_key:
            copy["evidence_fetch_warning"] = errors_by_key[key]
        enriched.append(copy)
    return enriched


def attach_offline_evidence(entry: dict, evidence: dict[str, Any]) -> dict:
    """Test helper: attach pre-built evidence without Jira fetch."""
    out = deepcopy(entry)
    out["evidence"] = deepcopy(evidence)
    return out
