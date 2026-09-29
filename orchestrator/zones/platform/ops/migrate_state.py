#!/usr/bin/env python3
"""Migrate legacy runtime state files into .state/ (one-time, idempotent).

Usage:
    python orchestrator/zones/platform/ops/migrate_state.py --dry-run
    python orchestrator/zones/platform/ops/migrate_state.py --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from orchestrator.paths import (  # noqa: E402
    LEGACY_SESSION_DIRS,
    LEGACY_STATE_DIRS,
    LEGACY_STATE_FILES,
    STATE_DIR,
    WIZARD_SESSIONS_DIR,
)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _merge_session_file(src: Path, dest: Path, *, apply: bool) -> str:
    if not src.is_file():
        return "skip_missing"
    if not dest.exists() or _mtime(src) > _mtime(dest):
        action = "copy" if apply else "would_copy"
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        return action
    return "skip_newer_dest"


def _merge_state_file(src: Path, dest: Path, *, apply: bool) -> str:
    if not src.is_file():
        return "skip_missing"
    if not dest.exists():
        action = "move" if apply else "would_move"
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        return action
    if _mtime(src) > _mtime(dest):
        action = "replace" if apply else "would_replace"
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        return action
    return "skip_newer_dest"


def migrate(*, apply: bool = False) -> dict:
    actions: list[dict[str, str]] = []
    WIZARD_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    for legacy_dir in LEGACY_SESSION_DIRS:
        if not legacy_dir.is_dir():
            continue
        for src in legacy_dir.iterdir():
            if not src.is_file():
                continue
            dest = WIZARD_SESSIONS_DIR / src.name
            result = _merge_session_file(src, dest, apply=apply)
            actions.append({"kind": "session", "src": str(src), "dest": str(dest), "action": result})

    for src, dest in LEGACY_STATE_FILES:
        result = _merge_state_file(src, dest, apply=apply)
        actions.append({"kind": "state_file", "src": str(src), "dest": str(dest), "action": result})

    for legacy_dir, dest_dir in LEGACY_STATE_DIRS:
        if not legacy_dir.is_dir():
            continue
        for src in legacy_dir.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(legacy_dir)
            dest = dest_dir / rel
            if dest.exists() and _mtime(dest) >= _mtime(src):
                actions.append({"kind": "state_tree", "src": str(src), "dest": str(dest), "action": "skip_newer_dest"})
                continue
            action = "copy" if apply else "would_copy"
            if apply:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            actions.append({"kind": "state_tree", "src": str(src), "dest": str(dest), "action": action})

    payload = {
        "migrated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "apply": apply,
        "state_dir": str(STATE_DIR),
        "actions": actions,
    }
    log_path = STATE_DIR / "migrate_log.json"
    if apply:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate RO runtime state to .state/")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = migrate(apply=args.apply)
    print(json.dumps(result, indent=2))
    changed = [a for a in result["actions"] if not a["action"].startswith("skip")]
    return 0 if changed or args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
