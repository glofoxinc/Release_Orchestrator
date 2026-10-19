"""Resolve GitHub report-host repo per Jira ticket (18-repo exemplars + fabric override)."""

from __future__ import annotations

import re
from typing import Any

import config
import glofox_jira_routing as gjr


def _host_cfg() -> dict[str, Any]:
    root = getattr(config, "GITHUB", {}) or {}
    repos = root.get("report_host_repos") or {}
    return repos if isinstance(repos, dict) else {}


def resolve_report_host_repo(
    *,
    jira_key: str | None = None,
    summary: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Map ticket to glofoxinc host repo using workspace.yaml + repo-jira-exemplars.json."""
    cfg = _host_cfg()
    an_default = str(cfg.get("an_default") or gjr._ANALYZE_REPO)
    pic_corps = {**(cfg.get("pic_corp_repos") or {}), **gjr.pic_corp_repos_from_exemplars()}
    text = "\n".join(x for x in (summary, description) if x)

    explicit = gjr.detect_explicit_github_repo(text)
    project = gjr.detect_jira_project(jira_key, text)
    corp, corp_repo = gjr.detect_corp(text, pic_corps, prefer_text=summary or "")

    repo: str | None = None
    reason = ""
    confidence = "medium"

    if explicit:
        repo = explicit
        confidence = "high"
        reason = "Explicit GitHub repo in ticket text."
    elif gjr.is_fabric_pipeline_work(text):
        repo = gjr._FABRIC_REPO
        confidence = "high"
        reason = (
            "Fabric/lakehouse/gold layer, notebook, or ingestion work "
            "→ gf-fabric-fitnessbi."
        )
    elif project == "AN":
        if corp_repo:
            repo = corp_repo
            confidence = "high"
            reason = f"AN ticket with client/brand '{corp}' mapped to customize host repo."
        else:
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
        "routing_catalog": "repo-jira-exemplars",
        "training_repos": gjr.training_repo_count(),
        "an_default": an_default,
        "fabric_default": gjr._FABRIC_REPO,
        "pic_corp_repos": pic_corps,
    }


def split_github_repo(full_name: str | None) -> tuple[str | None, str | None]:
    raw = str(full_name or "").strip().strip("/")
    if "/" not in raw:
        return None, None
    owner, repo = raw.split("/", 1)
    return owner.strip() or None, repo.strip() or None
