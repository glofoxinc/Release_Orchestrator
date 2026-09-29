"""Compatibility package — implementation in ``orchestrator/web/``."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / "orchestrator" / "web")]
