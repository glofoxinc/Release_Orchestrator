"""Tests for SHIPIT reference schedule timezone extraction."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tckt_reference import _timezone_name_from_iso


def test_shipit_16769_offset_maps_to_chicago():
    assert _timezone_name_from_iso("2026-09-09T10:00:00.000-0500") == "America/Chicago"
    assert _timezone_name_from_iso("2026-09-09T16:30:00.000-0500") == "America/Chicago"
