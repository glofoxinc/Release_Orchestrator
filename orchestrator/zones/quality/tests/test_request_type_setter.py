"""Tests for the hardened Service Desk request-type setter."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from request_type_setter import (
    SetRequestTypeResult,
    default_audit_path,
    set_request_type,
)


def _transport(responses):
    i = {"n": 0}

    def t(method, path, payload):
        idx = i["n"]
        i["n"] += 1
        if idx >= len(responses):
            raise AssertionError(f"transport called unexpectedly at idx {idx}")
        return responses[idx]

    t.calls = i
    return t


class TestSetRequestTypeSuccess:
    def test_single_success(self):
        t = _transport([(200, "ok")])
        result = set_request_type(
            "TCKT-1",
            service_desk_id="1",
            request_type_id="100",
            transport=t,
            max_attempts=3,
            base_delay=0,
            jitter=False,
        )
        assert result.ok
        assert result.last_status == 200

    def test_retries_until_success(self):
        t = _transport([(503, "down"), (500, "down"), (201, "created")])
        result = set_request_type(
            "TCKT-1",
            service_desk_id="1",
            request_type_id="100",
            transport=t,
            max_attempts=5,
            base_delay=0,
            jitter=False,
            sleep=lambda _s: None,
        )
        assert result.ok
        assert result.attempts == 3

    def test_retries_on_429(self):
        t = _transport([(429, "slow"), (200, "ok")])
        result = set_request_type(
            "T-1",
            service_desk_id="1",
            request_type_id="2",
            transport=t,
            max_attempts=3,
            base_delay=0,
            jitter=False,
            sleep=lambda _s: None,
        )
        assert result.ok


class TestSetRequestTypeFailure:
    def test_exhausts_retries_on_transient(self):
        t = _transport([(503, "down")] * 5)
        result = set_request_type(
            "T-1",
            service_desk_id="1",
            request_type_id="2",
            transport=t,
            max_attempts=3,
            base_delay=0,
            jitter=False,
            sleep=lambda _s: None,
        )
        assert not result.ok
        assert "transient" in result.message.lower() or "503" in result.message
        assert result.last_status == 503

    def test_permanent_4xx_fails_fast(self):
        t = _transport([(400, "bad request")])
        result = set_request_type(
            "T-1",
            service_desk_id="1",
            request_type_id="2",
            transport=t,
            max_attempts=5,
            base_delay=0,
            jitter=False,
            sleep=lambda _s: None,
        )
        assert not result.ok
        assert result.last_status == 400
        assert "permanent" in result.message.lower() or "400" in result.message

    def test_missing_params_fails_early(self):
        t = _transport([])
        result = set_request_type(
            "",
            service_desk_id="1",
            request_type_id="2",
            transport=t,
            max_attempts=3,
            base_delay=0,
            jitter=False,
        )
        assert not result.ok
        assert "missing" in result.message

    def test_transport_exception_captured(self):
        def boom(method, path, payload):
            raise RuntimeError("no connection")

        result = set_request_type(
            "T-1",
            service_desk_id="1",
            request_type_id="2",
            transport=boom,
            max_attempts=2,
            base_delay=0,
            jitter=False,
            sleep=lambda _s: None,
        )
        assert not result.ok


class TestAuditLog:
    def test_successful_call_records_audit(self, tmp_path):
        audit = tmp_path / "audit.log"
        t = _transport([(200, "ok")])
        set_request_type(
            "T-1",
            service_desk_id="1",
            request_type_id="2",
            transport=t,
            max_attempts=3,
            base_delay=0,
            jitter=False,
            audit_path=audit,
        )
        lines = audit.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["issue_key"] == "T-1" and rec["ok"] is True

    def test_failed_call_records_audit(self, tmp_path):
        audit = tmp_path / "audit.log"
        t = _transport([(400, "bad")])
        set_request_type(
            "T-1",
            service_desk_id="1",
            request_type_id="2",
            transport=t,
            max_attempts=3,
            base_delay=0,
            jitter=False,
            audit_path=audit,
            sleep=lambda _s: None,
        )
        rec = json.loads(audit.read_text(encoding="utf-8").strip())
        assert rec["ok"] is False

    def test_audit_append_not_overwrite(self, tmp_path):
        audit = tmp_path / "audit.log"
        audit.write_text('{"existing": true}\n', encoding="utf-8")
        t = _transport([(200, "ok")])
        set_request_type(
            "T-2",
            service_desk_id="1",
            request_type_id="2",
            transport=t,
            max_attempts=3,
            base_delay=0,
            jitter=False,
            audit_path=audit,
        )
        assert len(audit.read_text(encoding="utf-8").strip().splitlines()) == 2

    def test_default_audit_path_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JRT_AUDIT_LOG", str(tmp_path / "custom.log"))
        assert default_audit_path() == tmp_path / "custom.log"


class TestResultSerialization:
    def test_to_dict_shape(self):
        r = SetRequestTypeResult(ok=True, attempts=2, last_status=200, message="ok")
        d = r.to_dict()
        assert d["ok"] is True and d["attempts"] == 2
