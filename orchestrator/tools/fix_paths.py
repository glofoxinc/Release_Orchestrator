#!/usr/bin/env python3
"""One-shot path fixups after orchestrator/ zone restructure. Safe to re-run."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKIP = {".git", ".venv", "build", "dist", "node_modules", "__pycache__", ".pytest_cache"}
SKIP_FILES = {"CHANGELOG.md", "fix_paths.py"}

REPLACEMENTS = [
    # Zone layout (longer paths first)
    ("orchestrator/zones/platform/ops/", "orchestrator/zones/platform/ops/"),  # idempotent anchor
    ("orchestrator/ops/", "orchestrator/zones/platform/ops/"),
    ("orchestrator\\ops\\", "orchestrator\\zones\\platform\\ops\\"),
    ("orchestrator/agents/review/", "orchestrator/zones/product/agents/review/"),
    ("orchestrator\\agents\\review\\", "orchestrator\\zones\\product\\agents\\review\\"),
    ("orchestrator/web/", "orchestrator/zones/product/ui/"),
    ("orchestrator\\web\\", "orchestrator\\zones\\product\\ui\\"),
    ("orchestrator/server/", "orchestrator/zones/product/mcp/"),
    ("orchestrator\\server\\", "orchestrator\\zones\\product\\mcp\\"),
    ("orchestrator/core/", "orchestrator/zones/product/engine/"),
    ("orchestrator\\core\\", "orchestrator\\zones\\product\\engine\\"),
    ("docs/fixtures/", "orchestrator/zones/quality/tests/fixtures/"),
    ("tests/fixtures/", "orchestrator/zones/quality/tests/fixtures/"),
    ("orchestrator/zones/quality/orchestrator/", "orchestrator/"),  # fix double-prefix mistakes
    # Docs and commands
    ("streamlit run app.py", "streamlit run orchestrator/entry/app.py"),
    ("python -m pytest tests/", "python -m pytest orchestrator/zones/quality/tests/"),
    ("python -m pytest orchestrator/zones/quality/tests/ -q", "python -m pytest orchestrator/zones/quality/tests/ -q"),
    ("docs/GUIDE.md", "orchestrator/zones/knowledge/guides/GUIDE.md"),
    ("docs/RUNBOOK.md", "orchestrator/zones/knowledge/guides/RUNBOOK.md"),
    ("docs/CHANGELOG.md", "orchestrator/zones/knowledge/guides/CHANGELOG.md"),
    ("docs/SETUP.md", "orchestrator/zones/knowledge/guides/SETUP.md"),
    ("docs/STATE.md", "orchestrator/zones/knowledge/guides/STATE.md"),
    ("docs/skills/", "orchestrator/zones/knowledge/skills/"),
    ("profiles/workspace.yaml", "orchestrator/zones/config/profiles/workspace.yaml"),
    ("requirements-mcp.txt", "orchestrator/zones/config/deps/requirements-mcp.txt"),
    ("requirements.txt", "orchestrator/zones/config/deps/requirements.txt"),
    # Legacy first-generation moves
    ("release_mcp/scripts/", "orchestrator/zones/platform/ops/"),
    ("release_mcp\\scripts\\", "orchestrator\\zones\\platform\\ops\\"),
    ("release_mcp/scripts", "orchestrator/zones/platform/ops"),
    ("release_mcp\\scripts", "orchestrator\\zones\\platform\\ops"),
    ('REPO_ROOT / "daily_review_agent"', 'REPO_ROOT / "orchestrator" / "zones" / "product" / "agents" / "review"'),
    ('/ "daily_review_agent" /', '/ "orchestrator" / "zones" / "product" / "agents" / "review" /'),
]

# Bare docs/ and tests/ only in command contexts (avoid matching inside words)
COMMAND_REPLACEMENTS = [
    (re.compile(r"(?<![\w/])docs/"), "orchestrator/zones/knowledge/guides/"),
    (re.compile(r"(?<![\w/])tests/"), "orchestrator/zones/quality/tests/"),
]

PROJECT_ROOT_PATTERNS = [
    (
        r"_PROJECT_ROOT = Path\(__file__\)\.resolve\(\)\.parent\.parent\b",
        "from orchestrator.paths import REPO_ROOT as _PROJECT_ROOT",
    ),
    (
        r"_REPO_ROOT = Path\(__file__\)\.resolve\(\)\.parent\.parent\b",
        "from orchestrator.paths import REPO_ROOT as _REPO_ROOT",
    ),
    (
        r"REPO_ROOT = Path\(__file__\)\.resolve\(\)\.parents\[1\]",
        "from orchestrator.paths import REPO_ROOT",
    ),
]


def _should_touch(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP:
        return False
    if path.name in SKIP_FILES:
        return False
    if path.suffix not in {".py", ".md", ".yaml", ".yml", ".ps1", ".mjs", ".json", ".toml", ".mdc"}:
        return False
    return True


def main() -> None:
    changed = 0
    for path in REPO.rglob("*"):
        if not path.is_file() or not _should_touch(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        orig = text
        for old, new in REPLACEMENTS:
            if old == new:
                continue
            text = text.replace(old, new)
        for pattern, repl in COMMAND_REPLACEMENTS:
            text = pattern.sub(repl, text)
        for pattern, repl in PROJECT_ROOT_PATTERNS:
            text = re.sub(pattern, repl, text)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            changed += 1
            print(f"updated: {path.relative_to(REPO)}")

    print(f"done ({changed} files updated)")


if __name__ == "__main__":
    main()
