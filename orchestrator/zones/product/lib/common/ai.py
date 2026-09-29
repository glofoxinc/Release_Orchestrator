"""AI enhancement helpers shared by jira-release-tool and weekly-update-tool.

The real OpenAI / Azure OpenAI client is *optional* — this module is designed
to fall back to deterministic, rule-based heuristics whenever:

* No ``OPENAI_API_KEY`` / ``AZURE_OPENAI_API_KEY`` is set, **or**
* The ``openai`` package isn't installed, **or**
* The API call raises any exception.

Every public function returns a fully usable result in offline mode so that
unit tests, CI pipelines and air-gapped environments behave identically.

Responsibilities
----------------
1. ``classify_progress_state`` — assign a ticket to
   ``delivered`` / ``in_progress`` / ``blocked`` / ``at_risk``.
2. ``summarize_release`` — 3-sentence exec brief from ticket list.
3. ``suggest_acceptance_criteria`` — bullet list from a description.
4. ``rate_risk`` — low/medium/high based on scope heuristics.

All functions accept an injectable ``llm`` callable ``(prompt) -> str`` for
testing the "online" branch without network IO.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

LLM = Callable[[str], str]


# ── Progress classification ─────────────────────────────────────────────────

_DELIVERED = {"done", "closed", "resolved", "shipped", "released", "deployed", "completed"}
_IN_PROGRESS = {"in progress", "in review", "in qa", "code review", "testing"}
_BLOCKED = {"blocked", "on hold", "paused"}
_AT_RISK_KW = {"delay", "slipped", "missed", "risk", "concern", "escalate", "late"}


@dataclass
class ProgressState:
    state: str                       # delivered | in_progress | blocked | at_risk
    confidence: float                # 0..1
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "confidence": round(self.confidence, 3), "reason": self.reason}


def classify_progress_state(
    *,
    status: str = "",
    description: str = "",
    blocker: str = "",
    days_since_update: int | None = None,
    stale_threshold_days: int = 7,
) -> ProgressState:
    """Deterministically classify a ticket into a progress state."""
    s = (status or "").strip().lower()
    blocker_txt = (blocker or "").strip()
    desc = (description or "").strip()

    if s in _DELIVERED:
        return ProgressState("delivered", 0.95, f"status={status}")

    if s in _BLOCKED or (blocker_txt and blocker_txt.lower() not in {"", "none", "n/a", "no blockers"}):
        reason = "explicit blocker" if blocker_txt else f"status={status}"
        return ProgressState("blocked", 0.9, reason)

    stale = days_since_update is not None and days_since_update >= stale_threshold_days
    lowered = " ".join([s, desc, blocker_txt]).lower()
    at_risk_hit = any(kw in lowered for kw in _AT_RISK_KW)
    if stale or at_risk_hit:
        reason_parts = []
        if at_risk_hit:
            reason_parts.append("risk keyword")
        if stale:
            reason_parts.append(f"no update in {days_since_update}d")
        return ProgressState("at_risk", 0.7, ", ".join(reason_parts))

    return ProgressState("in_progress", 0.6 if s in _IN_PROGRESS else 0.4, f"status={status}")


# ── Risk rating ─────────────────────────────────────────────────────────────

@dataclass
class RiskAssessment:
    level: str                       # low | medium | high
    score: int
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "score": self.score, "signals": list(self.signals)}


_RISK_KEYWORDS = {
    "revenue": 3, "payment": 3, "security": 4, "rls": 3, "migrate": 2,
    "semantic model": 2, "production": 2, "breaking": 3, "schema": 2,
    "rename": 1, "delete": 2, "refactor": 2, "embed": 2, "capacity": 2,
}


def rate_risk(
    *,
    ticket_count: int,
    client_count: int,
    dashboard_count: int,
    text_blob: str = "",
) -> RiskAssessment:
    """Score release risk based on scope and keyword signals."""
    signals: list[str] = []
    score = 0

    if ticket_count >= 25:
        score += 3
        signals.append(f"{ticket_count} tickets")
    elif ticket_count >= 10:
        score += 2
        signals.append(f"{ticket_count} tickets")
    elif ticket_count >= 5:
        score += 1

    if client_count >= 5:
        score += 3
        signals.append(f"{client_count} clients")
    elif client_count >= 2:
        score += 1

    if dashboard_count >= 8:
        score += 2
        signals.append(f"{dashboard_count} dashboards")
    elif dashboard_count >= 4:
        score += 1

    lowered = (text_blob or "").lower()
    for kw, weight in _RISK_KEYWORDS.items():
        if kw in lowered:
            score += weight
            signals.append(kw)

    if score >= 10:
        level = "high"
    elif score >= 5:
        level = "medium"
    else:
        level = "low"
    return RiskAssessment(level=level, score=score, signals=signals)


# ── Summary ─────────────────────────────────────────────────────────────────

def _top_verbs(descriptions: Iterable[str]) -> list[str]:
    verbs: list[str] = []
    for d in descriptions:
        m = re.match(r"\s*(add|fix|update|refactor|remove|rename|improve|standardise|standardize|new)\b", d or "", re.I)
        if m:
            verbs.append(m.group(1).lower())
    seen: list[str] = []
    for v in verbs:
        if v not in seen:
            seen.append(v)
    return seen


def _offline_summary(tickets: list[dict[str, Any]]) -> str:
    n = len(tickets)
    if n == 0:
        return "No tickets were included in this release."
    clients = {t.get("client") for t in tickets if t.get("client") and t.get("client") != "Standard"}
    standard = any(t.get("client") == "Standard" or t.get("type") == "Analyze" for t in tickets)
    scope = []
    if standard:
        scope.append("Standard")
    if clients:
        scope.append("Custom ({})".format(", ".join(sorted(c for c in clients if c))))
    scope_txt = " and ".join(scope) or "selected"
    verbs = _top_verbs(t.get("description", "") for t in tickets)
    verb_txt = ", ".join(verbs[:3]) if verbs else "various improvements"
    dash_count = len({
        (t.get("client") or "Standard") + "|" + (t.get("report") or "")
        for t in tickets
    })
    return (
        f"This release bundles {n} tickets across {scope_txt} environments, "
        f"touching roughly {dash_count} dashboard/report(s). "
        f"Key themes: {verb_txt}. "
        "Deployment is low-to-moderate risk; validate in the standard rollout window."
    )


def summarize_release(
    tickets: list[dict[str, Any]],
    *,
    llm: LLM | None = None,
) -> str:
    """Return a 3-sentence executive brief for a release ticket list."""
    offline = _offline_summary(tickets)
    if llm is None and not _provider_available():
        return offline
    prompt = (
        "Summarise the following Jira tickets in exactly three sentences for a "
        "release announcement. Avoid emojis. Start with 'This release'.\n\n"
        + "\n".join(
            f"- {t.get('ticket', '?')}: {t.get('description', '') or t.get('summary', '')}"
            for t in tickets[:40]
        )
    )
    call = llm or _resolve_llm()
    try:
        text = (call(prompt) or "").strip()
        if text:
            return text
    except Exception:
        logger.debug("LLM summary failed; using offline", exc_info=True)
    return offline


# ── Acceptance criteria ─────────────────────────────────────────────────────

def _offline_acceptance_criteria(description: str) -> list[str]:
    desc = (description or "").strip()
    if not desc:
        return []
    bullets: list[str] = []
    # Identify explicit numbered/bulleted lines and rephrase.
    for ln in desc.splitlines():
        ln = ln.strip().lstrip("-•*0123456789. ").strip()
        if ln:
            bullets.append(ln)
    if not bullets:
        bullets = [desc]
    out: list[str] = []
    seen: set[str] = set()
    for b in bullets:
        short = re.sub(r"\s+", " ", b).strip().rstrip(".")
        key = short.lower()
        if not short or key in seen:
            continue
        seen.add(key)
        out.append(f"Given the change is deployed, when a user views the affected area, they should see: {short}.")
        if len(out) >= 8:
            break
    return out


def suggest_acceptance_criteria(
    description: str,
    *,
    llm: LLM | None = None,
) -> list[str]:
    """Return a list of acceptance-criteria bullets."""
    offline = _offline_acceptance_criteria(description)
    if llm is None and not _provider_available():
        return offline
    prompt = (
        "Generate 3–6 acceptance criteria bullets in 'Given/When/Then' style "
        "for this change. Respond as a plain list, one per line, no numbering:\n\n"
        + description
    )
    call = llm or _resolve_llm()
    try:
        text = (call(prompt) or "").strip()
        lines = [ln.strip("-• ").strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            return lines
    except Exception:
        logger.debug("LLM acceptance criteria failed; using offline", exc_info=True)
    return offline


# ── Provider wiring ─────────────────────────────────────────────────────────

def _provider_available() -> bool:
    if os.environ.get("OPENAI_API_KEY"):
        return True
    if os.environ.get("AZURE_OPENAI_API_KEY") and os.environ.get("AZURE_OPENAI_ENDPOINT"):
        return True
    return False


def _resolve_llm() -> LLM:
    """Return a concrete LLM callable for the configured provider."""

    def _raise(prompt: str) -> str:
        raise RuntimeError("no LLM provider configured")

    if not _provider_available():
        return _raise
    try:
        if os.environ.get("AZURE_OPENAI_API_KEY"):
            from openai import AzureOpenAI  # type: ignore

            client = AzureOpenAI(
                api_key=os.environ["AZURE_OPENAI_API_KEY"],
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            )
            deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

            def call(prompt: str) -> str:
                resp = client.chat.completions.create(
                    model=deployment,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
                return resp.choices[0].message.content or ""

            return call

        from openai import OpenAI  # type: ignore

        client = OpenAI()
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

        def call_openai(prompt: str) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return resp.choices[0].message.content or ""

        return call_openai
    except Exception:  # pragma: no cover - requires real SDK
        logger.debug("LLM client init failed", exc_info=True)
        return _raise


__all__ = [
    "LLM",
    "ProgressState",
    "RiskAssessment",
    "classify_progress_state",
    "rate_risk",
    "summarize_release",
    "suggest_acceptance_criteria",
]
