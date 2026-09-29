"""Compatibility package — implementation in ``orchestrator/shared/common/``."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / "orchestrator" / "shared" / "common")]
