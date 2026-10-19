"""Glofox Jira → GitHub routing (18-repo training set + fabric override).

Canonical data: orchestrator/zones/config/assets/repo-jira-exemplars.json
(sync via zabc-suite-tools/assets/glofox-repo-jira-routing/sync_glofox_routing.ps1).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_ASSETS = Path(__file__).resolve().parents[2] / "config" / "assets" / "repo-jira-exemplars.json"
_FABRIC_REPO = "glofoxinc/gf-fabric-fitnessbi"
_ANALYZE_REPO = "glofoxinc/gf-insights-fitnessbi"
_FABRIC_RE = re.compile(
    r"\b(fabric|lakehouse|gold\s*layer|gold_layer|notebook|ingestion|databricks)\b",
    re.IGNORECASE,
)
_JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9]+)-(\d+)\b")
_GH_REPO = re.compile(
    r"github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)",
    re.IGNORECASE,
)
_SKIP_REPO_NAMES = frozenset({"gf-fabric-fitnessbi", "paginated-reports-mcp"})


def detect_jira_project(jira_key_or_url: str | None, text: str = "") -> str | None:
    blob = f"{jira_key_or_url or ''} {text or ''}"
    match = _JIRA_KEY.search(blob)
    return match.group(1).upper() if match else None


def is_fabric_pipeline_work(text: str) -> bool:
    return bool(_FABRIC_RE.search(text or ""))


def detect_explicit_github_repo(text: str) -> str | None:
    for match in _GH_REPO.finditer(text or ""):
        owner = match.group("owner")
        repo = match.group("repo")
        if repo.lower().endswith(".git"):
            repo = repo[:-4]
        if repo.lower() in _SKIP_REPO_NAMES:
            continue
        return f"{owner}/{repo}"
    return None


@lru_cache(maxsize=1)
def load_exemplars() -> dict[str, Any]:
    if not _ASSETS.is_file():
        return {"repos": []}
    return json.loads(_ASSETS.read_text(encoding="utf-8"))


def pic_corp_repos_from_exemplars() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in load_exemplars().get("repos") or []:
        github = str(entry.get("github") or "").strip()
        if not github or entry.get("scope") == "fabric_data":
            continue
        if github == _ANALYZE_REPO:
            continue
        for keyword in entry.get("titleKeywords") or []:
            key = str(keyword).strip().lower()
            if key:
                mapping[key] = github
        display = str(entry.get("clientDisplayName") or "").strip().lower()
        if display:
            mapping[display] = github
        tenant = str(entry.get("tenantCode") or "").strip().lower()
        if tenant:
            mapping[tenant.replace("corp_", "")] = github
            mapping[tenant] = github
    aliases = {
        "club pilates": "glofoxinc/abc-customize-insights-xpo",
        "club pilates/xpo": "glofoxinc/abc-customize-insights-xpo",
        "lift -": "glofoxinc/abc-customize-insights-lift",
        "lift brands": "glofoxinc/abc-customize-insights-lift",
        "corp_yogaone": "glofoxinc/abc-customize-insights-yogaone",
        "corp_setshybrid": "glofoxinc/abc-customize-insights-setshybridtraining",
        "bd gyms": "glofoxinc/abc-customize-insights-BDGyms",
        "fs8 sk": "glofoxinc/abc-customize-insights-FS8-SouthKorea",
        "chin music": "glofoxinc/abc-customize-ChinMusic",
    }
    for key, repo in aliases.items():
        mapping.setdefault(key, repo)
    return mapping


def _detect_corp_in_blob(blob: str, mapping: dict[str, str]) -> tuple[str | None, str | None]:
    lowered = (blob or "").lower()
    for corp in sorted(mapping.keys(), key=len, reverse=True):
        if corp in lowered:
            return corp, mapping[corp]
    return None, None


def detect_corp(
    text: str,
    corps: dict[str, str] | None = None,
    *,
    prefer_text: str | None = None,
) -> tuple[str | None, str | None]:
    mapping = corps if corps is not None else pic_corp_repos_from_exemplars()
    if prefer_text:
        hit = _detect_corp_in_blob(prefer_text, mapping)
        if hit[0]:
            return hit
    return _detect_corp_in_blob(text or "", mapping)


def training_repo_count() -> int:
    return len(load_exemplars().get("repos") or [])
