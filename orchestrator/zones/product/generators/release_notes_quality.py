"""Release-notes text quality: cleaning, parsing fixes, and section builders.

Turns raw Jira ticket extractions into release-note-ready Key Highlights and
Dashboards / Reports lines that match the ABC Fitness reference style
(e.g. Release Notes 2026.3.07.15 / TCKT-102259 consolidation rules).
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from consolidation import consolidate_dashboards, dashboard_label

# Client names commonly used in PIC summaries. Longer names first for prefix match.
KNOWN_CUSTOM_CLIENTS: tuple[str, ...] = (
    "SETS Hybrid Training",
    "Cliste Hospitality",
    "Xtreme Fitness",
    "XtremeFitness",
    "Snap Fitness",
    "Energie UK",
    "Jazzercise",
    "ChinMusic",
    "FIT4MOM",
    "YogaOne",
    "Jetts",
    "Lift",
    "XPO",
    "FWBC",
)

# Display names from abc-bi-core.mdc. User-facing output must use these exact
# spellings, so "XtremeFitness" and "Jett's" normalize to the canonical form.
CLIENT_DISPLAY_NAMES: tuple[str, ...] = (
    "ChinMusic",
    "Cliste Hospitality",
    "Energie UK",
    "FIT4MOM",
    "FWBC",
    "Jazzercise",
    "Jetts",
    "Lift",
    "SETS Hybrid Training",
    "Snap Fitness",
    "XPO",
    "Xtreme Fitness",
    "YogaOne",
)


def _squash(name: str) -> str:
    """Reduce a client name to comparable letters/digits only."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


_CLIENT_BY_SQUASHED = {_squash(name): name for name in CLIENT_DISPLAY_NAMES}

# Common typos seen in Jira summaries that leak into published release notes.
_TYPO_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[Mm]ontly\b"), "Monthly"),
    (re.compile(r"\b[Pp]agianted\b"), "Paginated"),
    (re.compile(r"\b[Pp]oitning\b"), "pointing"),
    (re.compile(r"\b[Rr]eportting\b"), "reporting"),
    (re.compile(r"\b[Mm]emeber\b"), "Member"),
    (re.compile(r"\b[Mm]emebrship\b"), "Membership"),
    (re.compile(r"\b[Dd]ahsboard\b"), "Dashboard"),
    (re.compile(r"\b[Ss]ematic\b"), "semantic"),
)

_ANALYZE_PREFIX = re.compile(
    r"^(?:analyze|standard(?:\s*\(analyze\))?|an)\s*[-–—:]\s*",
    re.IGNORECASE,
)
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:])")
_MISSING_SPACE_AFTER_PAREN = re.compile(r"\)(?=[A-Za-z])")
_MISSING_SPACE_BEFORE_PAREN = re.compile(r"(?<=[A-Za-z])\(")
_DASH_NORMALIZE = re.compile(r"\s+[-–—]\s+")

# Report stubs that are never useful alone as a dashboard name.
_WEAK_REPORT = re.compile(
    r"^(?:analyze|standard|an|e|n\/?a|tbd|todo|fix|update|updates|change|changes)$",
    re.IGNORECASE,
)

DEFAULT_ANALYZE_CLIENTS_BULLET = "All Analyze-based (Standard) clients"
DEFAULT_CUSTOM_CLIENTS_INTRO = (
    "This release includes updates to existing functionality, semantic model changes, "
    "column additions, and new report creation for custom clients."
)


def clean_release_text(text: str) -> str:
    """Normalize whitespace, punctuation, and common release-note typos."""
    if not text:
        return ""
    out = str(text).replace("\u00a0", " ").strip()
    out = out.strip("\"'")
    for pattern, replacement in _TYPO_FIXES:
        out = pattern.sub(replacement, out)
    out = _MISSING_SPACE_AFTER_PAREN.sub(") ", out)
    out = _MISSING_SPACE_BEFORE_PAREN.sub(" (", out)
    # "report)-Transaction" / "report)- Transaction" → "report) - Transaction"
    out = re.sub(r"\)\s*-\s*(?=[A-Za-z])", ") - ", out)
    out = _MULTI_SPACE.sub(" ", out)
    out = _SPACE_BEFORE_PUNCT.sub(r"\1", out)
    out = _DASH_NORMALIZE.sub(" - ", out)
    # Prefer consistent casing for the phrase "paginated report".
    out = re.sub(r"\bpaginated report\b", "paginated report", out, flags=re.IGNORECASE)
    out = re.sub(r"\bnew paginated report\b", "New paginated report", out, flags=re.IGNORECASE)
    return out.strip(" -")


def is_weak_report_name(report: str) -> bool:
    """True when a report label is too short/generic to stand alone."""
    cleaned = clean_release_text(report)
    if not cleaned:
        return True
    if len(cleaned) <= 2:
        return True
    return bool(_WEAK_REPORT.match(cleaned))


def match_known_client(prefix: str) -> tuple[str, str] | None:
    """If ``prefix`` starts with a known client, return ``(client, remainder)``."""
    text = (prefix or "").strip()
    if not text:
        return None
    lower = text.lower()
    for client in KNOWN_CUSTOM_CLIENTS:
        cl = client.lower()
        if lower == cl:
            return client, ""
        if lower.startswith(cl + " ") or lower.startswith(cl + "-"):
            rest = text[len(client) :].lstrip(" -–—")
            return client, rest
    return None


def canonical_client_name(name: str) -> str:
    """Return the display-name spelling for a client, or the input unchanged."""
    cleaned = clean_release_text(name)
    if not cleaned:
        return ""
    return _CLIENT_BY_SQUASHED.get(_squash(cleaned), cleaned)


def improve_extracted_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a cleaned copy of one extracted ticket dict."""
    improved = dict(entry)
    ticket_type = (improved.get("type") or "").strip()
    report = clean_release_text(improved.get("report") or "")
    description = clean_release_text(improved.get("description") or "")
    client = clean_release_text(improved.get("client") or "")

    if ticket_type == "Analyze":
        report = _ANALYZE_PREFIX.sub("", report).strip(" -")
        # "Analyze - Payout Item Details..." often leaves report="Analyze".
        if is_weak_report_name(report) and description:
            # Prefer the first clause of the description as the report name.
            parts = _DASH_NORMALIZE.split(description, maxsplit=1)
            report = clean_release_text(parts[0]) or description
            description = clean_release_text(parts[1]) if len(parts) > 1 else description
            if description.lower() == report.lower():
                # Keep a useful description when we only had a stub report.
                pass
        client = "Standard"
    else:
        matched = match_known_client(client)
        if matched:
            known_client, remainder = matched
            client = known_client
            if remainder:
                # "FWBC Customize Pulse Report - Minor Reconfiguration Needed"
                # → client=FWBC, report=Customize Pulse Report, description=Minor…
                if is_weak_report_name(report) or report.lower() == description.lower():
                    if report and report.lower() != remainder.lower():
                        description = report
                    report = clean_release_text(remainder)
                elif remainder.lower() not in report.lower():
                    report = clean_release_text(f"{remainder} - {report}")
        client = canonical_client_name(client)

    if description.lower() == report.lower():
        # Keep identical values; builders treat this as redundant.
        description = report

    improved["client"] = client
    improved["report"] = report
    improved["description"] = description
    return improved


def improve_extracted(extracted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean and repair every extracted ticket entry."""
    return [improve_extracted_entry(e) for e in extracted or []]


def _highlight_body(entry: dict[str, Any]) -> str:
    report = (entry.get("report") or "").strip()
    description = (entry.get("description") or "").strip()
    redundant = not description or description.lower() == report.lower()

    if entry.get("type") == "Analyze":
        if redundant:
            return f"Updates to {report}" if report else "Reporting updates"
        return f"Updates to {report}: {description}"

    if redundant:
        return report or description
    if report and description:
        return f"{report}: {description}"
    return report or description


def build_key_highlight_lines(extracted: list[dict[str, Any]]) -> list[str]:
    """Build polished Key Highlights lines from extracted tickets.

    Improvements over the naive one-line-per-raw-ticket approach:
    - Cleans common typos and spacing
    - Repairs weak Analyze report names (e.g. ``E``, ``Analyze``)
    - Groups Custom highlights under the real client name
    - Dedupes identical bodies
    """
    cleaned = improve_extracted(extracted)
    lines: list[str] = []
    seen: set[str] = set()

    # Preserve ticket order while grouping Custom lines after their first client appearance.
    custom_buckets: OrderedDict[str, list[str]] = OrderedDict()
    analyze_bodies: list[str] = []

    for entry in cleaned:
        body = _highlight_body(entry).strip(" :")
        if not body:
            continue
        key = body.lower()
        if key in seen:
            continue
        seen.add(key)

        if entry.get("type") == "Analyze":
            analyze_bodies.append(body)
        else:
            label = (entry.get("client") or "").strip() or "Custom"
            custom_buckets.setdefault(label, []).append(body)

    for client, bodies in custom_buckets.items():
        for body in bodies:
            lines.append(f"{client}: {body}")
    for body in analyze_bodies:
        lines.append(f"Standard (Analyze): {body}")
    return lines


def build_dashboard_lines(extracted: list[dict[str, Any]]) -> list[str]:
    """Build consolidated Dashboards / Reports bullets.

    Format matches the reference docs:
    - Custom: ``Client - Report`` (append `` – summary`` when useful)
    - Analyze: ``Analyze - Report`` (spaces around the dash; never ``Analyze-``)
    """
    cleaned = improve_extracted(extracted)
    consolidated = consolidate_dashboards(cleaned)
    lines: list[str] = []
    seen: set[str] = set()

    for item in consolidated:
        entries = item.get("entries") or []
        sample = entries[0] if entries else {}
        summary = clean_release_text(item.get("summary") or "")
        report = clean_release_text(sample.get("report") or item.get("label") or "")
        client = clean_release_text(sample.get("client") or "")

        if sample.get("type") == "Custom" or (client and client != "Standard"):
            prefix = client or report
            # Prefer report for the right-hand side; fall back to label remainder.
            label = dashboard_label(sample) if sample else item.get("label", "")
            if " - " in label:
                _, rhs = label.split(" - ", 1)
                report = clean_release_text(rhs) or report
            if is_weak_report_name(report) and summary:
                report = summary.split(",")[0].strip()
            line = f"{prefix} - {report}" if report and report.lower() != prefix.lower() else prefix
        else:
            if is_weak_report_name(report):
                report = clean_release_text(summary.split(",")[0] if summary else "") or report
            if not report:
                continue
            line = f"Analyze - {report}"

        line = clean_release_text(line)
        key = line.lower()
        if not line or key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def build_custom_clients_list(extracted: list[dict[str, Any]]) -> list[str]:
    """Distinct custom client names, cleaned and sorted."""
    cleaned = improve_extracted(extracted)
    names: list[str] = []
    seen: set[str] = set()
    for entry in cleaned:
        if entry.get("type") != "Custom":
            continue
        client = (entry.get("client") or "").strip()
        if not client or client in ("Unknown", "Standard"):
            continue
        # Reject values that still look like full report titles.
        if re.search(r"\b(report|dashboard|paginated)\b", client, re.IGNORECASE) and " " in client:
            matched = match_known_client(client)
            if matched:
                client = canonical_client_name(matched[0])
            else:
                continue
        key = client.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(client)
    return sorted(names, key=str.lower)


def assess_release_notes_quality(
    *,
    highlight_lines: list[str] | None = None,
    dashboard_lines: list[str] | None = None,
    analyze_clients: str = "",
    custom_clients: list[str] | str | None = None,
) -> list[str]:
    """Return human-readable quality warnings for the edit/preview UI."""
    warnings: list[str] = []
    highlights = highlight_lines or []
    dashboards = dashboard_lines or []

    for line in highlights:
        low = line.lower()
        if re.search(r"\b(montly|pagianted|poitning)\b", low):
            warnings.append(f"Possible typo in Key Highlights: “{line}”")
        if re.search(r"updates to [a-z](?:\s|:|$)", low) or "updates to analyze" in low:
            warnings.append(
                f"Weak Analyze highlight (report name looks incomplete): “{line}”"
            )
        if re.search(r"(?i)analyze-\s", line) or re.search(r"(?i)analyze-\S", line):
            warnings.append(f"Use “Analyze - …” with spaces, not “Analyze-”: “{line}”")

    for line in dashboards:
        if re.match(r"(?i)analyze-\s", line) or re.match(r"(?i)analyze-\S", line):
            warnings.append(f"Dashboard line missing spaces around dash: “{line}”")
        if re.match(r"(?i)analyze\s*-\s*[a-z]$", line) or re.match(
            r"(?i)analyze\s*-\s*analyze$", line
        ):
            warnings.append(f"Incomplete Dashboards / Reports entry: “{line}”")
        if re.search(r"\b(montly|pagianted|poitning)\b", line, re.IGNORECASE):
            warnings.append(f"Possible typo in Dashboards / Reports: “{line}”")

    analyze = (analyze_clients or "").strip()
    if analyze and analyze.lower() in {"analyze clients", "analyze client", "standard"}:
        warnings.append(
            'Prefer “All Analyze-based (Standard) clients” for the Analyze Clients bullet.'
        )

    if isinstance(custom_clients, str):
        custom_list = [c.strip() for c in custom_clients.split(",") if c.strip()]
    else:
        custom_list = list(custom_clients or [])
    for name in custom_list:
        if re.search(r"\b(report|dashboard|paginated)\b", name, re.IGNORECASE):
            warnings.append(
                f"Custom client name looks like a report title: “{name}”. "
                "Use the client only (e.g. FWBC)."
            )

    # Deduplicate while preserving order
    return list(dict.fromkeys(warnings))


def prepare_change_table_entries(
    extracted: list[dict[str, Any]],
    *,
    test_by_names: list[str] | None = None,
    testing_statuses: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Clean extracted tickets for the Ticket Details table.

    Applies the same typo / weak-report / client-name repairs used for
    Key Highlights and Reports / Dashboards Delivered, so the Ticket Details
    rows do not ship stubs like ``Report=E`` or ``Client=XtremeFitness``.

    ``testing_statuses`` (when provided) fills Testing Status — typically
    ``ETL Done`` for Mona-owned ETL tickets and ``Done`` for everyone else.
    """
    cleaned = improve_extracted(extracted)
    rows: list[dict[str, Any]] = []
    for idx, entry in enumerate(cleaned):
        report = (entry.get("report") or "").strip()
        description = (entry.get("description") or "").strip()
        client = (entry.get("client") or "").strip()
        if entry.get("type") == "Analyze":
            client = "Standard"
        else:
            client = canonical_client_name(client) or client

        test_by = ""
        if test_by_names is not None and idx < len(test_by_names):
            test_by = test_by_names[idx] or ""
        elif entry.get("test_by"):
            test_by = str(entry.get("test_by") or "")

        testing_status = ""
        if testing_statuses is not None and idx < len(testing_statuses):
            testing_status = testing_statuses[idx] or ""
        elif entry.get("testing_status"):
            testing_status = str(entry.get("testing_status") or "")

        rows.append({
            "sno": str(entry.get("sno") or idx + 1),
            "ticket": entry.get("ticket") or "",
            "parent_epic": (
                entry.get("parent_epic")
                or entry.get("parent")
                or entry.get("ticket")
                or ""
            ),
            "link": entry.get("link") or "",
            "type": entry.get("type") or "",
            "client": client,
            "report": report,
            "description": description,
            "assignee": str(entry.get("assignee") or "").strip(),
            "test_by": test_by,
            "comments": entry.get("comments") or "",
            "testing_status": testing_status,
        })
    return rows


__all__ = [
    "CLIENT_DISPLAY_NAMES",
    "DEFAULT_ANALYZE_CLIENTS_BULLET",
    "DEFAULT_CUSTOM_CLIENTS_INTRO",
    "KNOWN_CUSTOM_CLIENTS",
    "assess_release_notes_quality",
    "build_custom_clients_list",
    "build_dashboard_lines",
    "build_key_highlight_lines",
    "canonical_client_name",
    "clean_release_text",
    "improve_extracted",
    "improve_extracted_entry",
    "is_weak_report_name",
    "match_known_client",
    "prepare_change_table_entries",
]
