"""Compatibility package — implementation in ``zones/product/generators/``."""

from pathlib import Path

_ZONES = Path(__file__).resolve().parents[3]
__path__ = [str(_ZONES / "product" / "generators")]
