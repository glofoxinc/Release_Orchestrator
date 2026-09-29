"""Compatibility package — implementation in ``zones/product/agents/review/``."""

from pathlib import Path

_ZONES = Path(__file__).resolve().parents[3]
__path__ = [str(_ZONES / "product" / "agents" / "review")]
