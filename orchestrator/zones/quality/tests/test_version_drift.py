"""Package version must match README and skill headers."""

from __future__ import annotations

import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[4]


def _package_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_readme_contains_package_version():
    version = _package_version()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert version in readme, f"README.md must mention package version {version}"


def test_skill_header_matches_package_version():
    version = _package_version()
    skill = ROOT / "orchestrator" / "zones" / "knowledge" / "skills" / "release-orchestrator-mcp" / "SKILL.md"
    assert skill.is_file(), "orchestrator/zones/knowledge/skills/release-orchestrator-mcp/SKILL.md is required"
    text = skill.read_text(encoding="utf-8")
    match = re.search(r"v(\d+\.\d+\.\d+)", text)
    assert match, "Skill should declare a semver"
    assert match.group(1) == version


def test_skill_folder_matches_frontmatter_name():
    skill = ROOT / "orchestrator" / "zones" / "knowledge" / "skills" / "release-orchestrator-mcp" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    name_match = re.search(r"^name:\s*(\S+)", text, re.MULTILINE)
    assert name_match, "Skill frontmatter must include name:"
    assert name_match.group(1) == "release-orchestrator-mcp"
    assert skill.parent.name == "release-orchestrator-mcp"
