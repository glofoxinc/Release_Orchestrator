"""Resolve GitHub report-host repo per Jira ticket (AN default + PIC corp map)."""

from __future__ import annotations

import re
from typing import Any

import config

_JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9]+)-(\d+)\b")
_GH_REPO = re.compile(
    r"github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)",
    re.IGNORECASE,
)


def _host_cfg() -> dict[str, Any]:
    root = getattr(config, "GITHUB", {}) or {}
    repos = root.get("report_host_repos") or {}
    return repos if isinstance(repos, dict) else {}


def detect_jira_project(jira_key_or_url: str | None, text: str = "") -> str | None:
    blob = f"{jira_key_or_url or ''} {text or ''}"
    match = _JIRA_KEY.search(blob)
    return match.group(1).upper() if match else None


def detect_explicit_github_repo(text: str) -> str | None:
    for match in _GH_REPO.finditer(text or ""):
        owner = match.group("owner")
        repo = match.group("repo").rstrip(".git")
        skip = {"gf-fabric-fitnessbi", "paginated-reports-mcp"}
        if repo.lower() in skip:
            continue
        return f"{owner}/{repo}"
    return None


def detect_corp(text: str, corps: dict[str, str] | None = None) -> tuple[str | None, str | None]:
    mapping = corps if corps is not None else (_host_cfg().get("pic_corp_repos") or {})
    blob = (text or "").lower()
    for corp in sorted(mapping.keys(), key=len, reverse=True):
        if corp.lower() in blob:
            return corp, mapping[corp]
    return None, None


def resolve_report_host_repo(
    *,
    jira_key: str | None = None,
    summary: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Map ticket to glofoxinc/gf-insights-fitnessbi or corp customize repo."""
    cfg = _host_cfg()
    an_default = str(cfg.get("an_default") or "glofoxinc/gf-insights-fitnessbi")
    pic_corps = cfg.get("pic_corp_repos") or {}
    text = "\n".join(x for x in (summary, description) if x)

    explicit = detect_explicit_github_repo(text)
    project = detect_jira_project(jira_key, text)
    corp, corp_repo = detect_corp(text, pic_corps)

    repo: str | None = None
    reason = ""
    confidence = "medium"

    if explicit:
        repo = explicit
        confidence = "high"
        reason = "Explicit GitHub repo in ticket text."
    elif project == "AN":
        repo = an_default
        confidence = "high"
        reason = "AN ticket — default Analyze host repo."
    elif project == "PIC":
        if corp_repo:
            repo = corp_repo
            confidence = "high"
            reason = f"PIC customize — corp '{corp}' mapped to host repo."
        else:
            confidence = "low"
            reason = "PIC ticket — corp/brand not recognized for repo map."
    elif corp_repo:
        repo = corp_repo
        reason = f"Corp '{corp}' detected in text."
    elif re.search(r"\b(glofox|fitness\s*bi|fitnessbi)\b", text, re.I):
        repo = an_default
        reason = "Glofox/FitnessBI cues — using AN default repo."

    owner, repo_name = split_github_repo(repo) if repo else (None, None)
    return {
        "ok": bool(repo),
        "jira_project": project,
        "corp_detected": corp,
        "report_host_repo": repo,
        "owner": owner,
        "repo": repo_name,
        "confidence": confidence,
        "reason": reason,
        "an_default": an_default,
        "pic_corp_repos": pic_corps,
    }


def split_github_repo(full_name: str | None) -> tuple[str | None, str | None]:
    raw = str(full_name or "").strip().strip("/")
    if "/" not in raw:
        return None, None
    owner, repo = raw.split("/", 1)
    return owner.strip() or None, repo.strip() or None
