"""Append-only onboarding timing telemetry (local .state, gitignored)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.paths import STATE_DIR

_TELEMETRY_FILE = STATE_DIR / "onboarding_telemetry.jsonl"


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with _TELEMETRY_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass


def telemetry_path() -> Path:
    return _TELEMETRY_FILE
