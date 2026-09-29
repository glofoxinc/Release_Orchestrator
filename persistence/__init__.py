"""Compatibility package — implementation in ``orchestrator/shared/persistence/``."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / "orchestrator" / "shared" / "persistence")]
