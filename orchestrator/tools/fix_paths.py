#!/usr/bin/env python3
"""One-shot path fixups after orchestrator/ restructure. Safe to re-run."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKIP = {".git", ".venv", "build", "dist", "node_modules", "__pycache__", ".pytest_cache"}

REPLACEMENTS = [
    ("release_mcp/scripts/", "orchestrator/ops/"),
    ("release_mcp\\scripts\\", "orchestrator\\ops\\"),
    ("release_mcp/scripts", "orchestrator/ops"),
    ("release_mcp\\scripts", "orchestrator\\ops"),
    ('Path(__file__).resolve().parent.parent / ".launch"', 'Path(__file__).resolve().parents[2] / ".launch"'),
    ('Path(__file__).resolve().parent.parent / "output"', 'Path(__file__).resolve().parents[2] / "output"'),
    ('REPO_ROOT / "daily_review_agent"', 'REPO_ROOT / "orchestrator" / "agents" / "review"'),
    ('/ "daily_review_agent" /', '/ "orchestrator" / "agents" / "review" /'),
    ('"daily_review_agent/', '"orchestrator/agents/review/'),
    ("daily_review_agent/agent.yaml", "orchestrator/agents/review/agent.yaml"),
    ("daily_review_agent/setup_mcp.py", "orchestrator/agents/review/setup_mcp.py"),
    ("daily_review_agent/onboarding.py", "orchestrator/agents/review/onboarding.py"),
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
    if path.suffix not in {".py", ".md", ".yaml", ".yml", ".ps1", ".mjs", ".json", ".toml", ".mdc"}:
        return False
    if path.name == "fix_paths.py":
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
            text = text.replace(old, new)
        for pattern, repl in PROJECT_ROOT_PATTERNS:
            text = re.sub(pattern, repl, text)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            changed += 1
            print(f"updated: {path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
    print("done")
