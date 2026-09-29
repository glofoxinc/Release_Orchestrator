"""Compatibility package — implementation in ``zones/product/lib/persistence/``."""

from pathlib import Path

_ZONES = Path(__file__).resolve().parents[3]
__path__ = [str(_ZONES / "product" / "lib" / "persistence")]
