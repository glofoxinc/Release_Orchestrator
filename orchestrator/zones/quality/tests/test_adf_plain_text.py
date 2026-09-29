"""Tests for ADF plain-text round-trip helpers."""

from __future__ import annotations

import adf_builder as adf


def test_adf_to_plain_text_paragraphs_and_bullets():
    doc = adf.doc(
        adf.paragraph(adf.text("Hello")),
        adf.spacer(),
        adf.paragraph(adf.text("Affected Clients:", bold=True)),
        adf.bullet_item(adf.text("Lift - AIA", bold=True), adf.text(" migration")),
    )
    plain = adf.adf_to_plain_text(doc)
    assert "Hello" in plain
    assert "Affected Clients:" in plain
    assert "- Lift - AIA migration" in plain


def test_plain_text_to_doc_bullets_and_paragraphs():
    plain = "Intro line\n\nAffected Clients:\n\n- Item one\n- Item two"
    doc = adf.plain_text_to_doc(plain)
    assert doc["type"] == "doc"
    assert len(doc["content"]) >= 3


def test_plain_text_round_trip_preserves_bullets():
    original = "Summary\n\n- Alpha\n- Beta"
    round_trip = adf.adf_to_plain_text(adf.plain_text_to_doc(original))
    assert "Alpha" in round_trip
    assert "Beta" in round_trip
