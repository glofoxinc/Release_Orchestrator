"""Glofox vs Ignite program packs must not share crew."""

from __future__ import annotations

import program_pack as pp


def test_glofox_pack_is_trained_with_review_call_roles():
    pack = pp.load_program("glofox")
    assert pack["trained"] is True
    assert pack["projects"] == ["PIC", "AN"]
    names = set(pp.crew_names(pack, "squad"))
    assert "Lakshmi Narasimha" in names
    assert "Rekha" in names
    qa = set(pp.crew_names(pack, "qa"))
    assert "Akhil Sree Kumar" in qa
    assert "Nikhila Sree Ramisetti" in qa
    leaders = set(pp.crew_names(pack, "leadership"))
    assert "Sushma Bhamidipati" in leaders
    assert "Soumyakant Mishra" in leaders
    exclude = set(pp.crew_names(pack, "exclude"))
    assert "Gabriel Barbosa" in exclude
    assert "Erasmo García" in exclude
    rules = pack["review_call"]
    assert "leadership" in rules["required_roles"]
    assert "qa" in rules["required_roles"]
    assert rules["slack_notify_skips_optional"] is True
    comments = pack["developer_comments"]["allowed"]
    assert comments == ["ready for review", "ready for release"]


def test_ignite_pack_is_empty_and_untrained():
    pack = pp.load_program("ignite")
    assert pack["trained"] is False
    assert pack["projects"] == ["PIC"]
    assert pp.crew_names(pack, "squad") == []
    assert pp.crew_names(pack, "qa") == []
    assert pp.crew_names(pack, "leadership") == []
    glofox_names = set(pp.crew_names(pp.load_program("glofox"), "squad"))
    assert not glofox_names.intersection(pp.crew_names(pack, "squad"))


def test_switch_ignite_is_blocked():
    out = pp.switch_program("ignite")
    assert out["ok"] is False
    assert out["clash_prevented"] is True
    assert "Glofox" in out["error"] or "glofox" in out["error"].lower()


def test_train_ignite_refuses_copy():
    out = pp.train_program("ignite")
    assert out["ok"] is False
    assert out["clash_prevented"] is True
    assert "glofox.yaml" in out["error"].lower() or "do not copy" in out["error"].lower()


def test_train_glofox_returns_full_context():
    out = pp.train_program("glofox")
    assert out["ok"] is True
    assert "Akhil Sree Kumar" in out["qa"]
    ctx = pp.program_context()
    assert ctx["program"] == "glofox"
    assert ctx["trained"] is True
    assert "never copy" in ctx["hint"].lower() or "Ignite" in ctx["hint"]
