"""Compatibility package — implementation in ``orchestrator/generators/``."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / "orchestrator" / "generators")]
