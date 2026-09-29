"""Skip tickets already reviewed (Jira comment markers) — status may unchanged."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import jira_client

logger = logging.getLogger(__name__)

DEFAULT_SKIP_PHRASES = (
    "review done",
    "reviewed",
    "review complete",
    "review completed",
    "daily review done",
    "no further review",
    "reviewed in daily",
)


@dataclass
class ReviewFilterConfig:
    enabled: bool = True
    check_comments: bool = True
    skip_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_SKIP_PHRASES))
    case_insensitive: bool = True


def _normalize_phrases(phrases: list[str]) -> list[str]:
    out: list[str] = []
    for raw in phrases:
        text = (raw or "").strip()
        if text and text not in out:
            out.append(text)
    return out or list(DEFAULT_SKIP_PHRASES)


def comment_indicates_review_done(body: dict | str, phrases: list[str], *, case_insensitive: bool = True) -> str | None:
    """Return matched phrase if comment body signals review is complete."""
    from jira_client import _comment_plain_text

    text = _comment_plain_text(body)
    if not text.strip():
        return None
    hay = text if not case_insensitive else text.lower()
    for phrase in _normalize_phrases(phrases):
        needle = phrase if not case_insensitive else phrase.lower()
        if needle in hay:
            return phrase
    return None


def issue_has_review_done_comment(issue_key: str, cfg: ReviewFilterConfig) -> str | None:
    """Return matched skip phrase if any comment on the issue marks review done."""
    if not cfg.enabled or not cfg.check_comments:
        return None
    try:
        comments = jira_client._iter_all_comments(issue_key)  # noqa: SLF001
    except Exception as exc:
        logger.warning("Comments unavailable for %s: %s", issue_key, exc)
        return None
    for comment in comments:
        body = comment.get("body")
        hit = comment_indicates_review_done(body, cfg.skip_phrases, case_insensitive=cfg.case_insensitive)
        if hit:
            return hit
    return None


def filter_already_reviewed(
    issues: list[dict],
    cfg: ReviewFilterConfig,
) -> tuple[list[dict], list[dict[str, str]]]:
    """Drop issues with review-done comments; return (kept, skipped_meta)."""
    if not cfg.enabled:
        return issues, []

    kept: list[dict] = []
    skipped: list[dict[str, str]] = []
    for issue in issues:
        key = str(issue.get("key") or "")
        if not key:
            kept.append(issue)
            continue
        matched = issue_has_review_done_comment(key, cfg)
        if matched:
            skipped.append({"key": key, "reason": f"comment marker: {matched}"})
            continue
        kept.append(issue)
    return kept, skipped
