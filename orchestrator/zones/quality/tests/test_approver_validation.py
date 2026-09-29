"""Tests for approver_validator pre-flight validation + caching."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

from approver_validator import (
    _CACHE_TTL_SECONDS,
    ApproverCheck,
    GroupCheck,
    ValidationResult,
    clear_cache,
    validate_approvers,
    validate_defaults,
    validate_groups,
)

APPROVERS = [
    {"accountId": "a1", "name": "Alice"},
    {"accountId": "a2", "name": "Bob"},
]
GROUPS = [{"name": "Command Center"}, {"name": "Fake Group"}]


def _user_lookup_all_ok(aid):
    return {"accountId": aid, "displayName": f"User {aid}"}


def _user_lookup_missing_a2(aid):
    if aid == "a2":
        return None
    return {"accountId": aid, "displayName": f"User {aid}"}


def _group_lookup_missing_fake(name):
    if name == "Fake Group":
        return None
    return {"name": name}


class TestValidateApprovers:
    def test_all_valid(self):
        checks = validate_approvers(APPROVERS, user_lookup=_user_lookup_all_ok)
        assert all(c.ok for c in checks)
        assert checks[0].display_name == "User a1"

    def test_missing_user(self):
        checks = validate_approvers(APPROVERS, user_lookup=_user_lookup_missing_a2)
        assert checks[0].ok
        assert not checks[1].ok
        assert "no longer exists" in checks[1].error

    def test_empty_account_id(self):
        checks = validate_approvers([{"accountId": "", "name": "X"}], user_lookup=_user_lookup_all_ok)
        assert not checks[0].ok
        assert "missing" in checks[0].error.lower()

    def test_lookup_exception_becomes_error(self):
        def raiser(aid):
            raise RuntimeError("network down")
        checks = validate_approvers([{"accountId": "x"}], user_lookup=raiser)
        assert not checks[0].ok
        assert "network down" in checks[0].error

    def test_string_account_ids(self):
        checks = validate_approvers(["a1"], user_lookup=_user_lookup_all_ok)
        assert checks[0].ok
        assert checks[0].account_id == "a1"


class TestValidateGroups:
    def test_all_valid(self):
        out = validate_groups([{"name": "A"}], group_lookup=lambda n: {"name": n})
        assert out[0].ok

    def test_missing_group(self):
        out = validate_groups(GROUPS, group_lookup=_group_lookup_missing_fake)
        assert out[0].ok
        assert not out[1].ok
        assert "does not exist" in out[1].error

    def test_string_group(self):
        out = validate_groups(["G"], group_lookup=lambda n: {"name": n})
        assert out[0].ok

    def test_empty_name(self):
        out = validate_groups([{"name": ""}], group_lookup=lambda n: {"name": n})
        assert not out[0].ok


class TestValidateDefaults:
    def test_aggregates_both(self):
        result = validate_defaults(
            APPROVERS, GROUPS,
            user_lookup=_user_lookup_all_ok,
            group_lookup=_group_lookup_missing_fake,
        )
        assert not result.all_ok
        assert len(result.approvers) == 2
        assert len(result.groups) == 2
        assert any("Fake Group" in m for m in result.failures)

    def test_cache_hit_within_ttl(self):
        cache: dict = {}
        counter = {"n": 0}

        def counting(aid):
            counter["n"] += 1
            return {"accountId": aid}

        validate_defaults(
            APPROVERS, [], cache=cache, user_lookup=counting,
            group_lookup=lambda n: {"name": n},
        )
        first_calls = counter["n"]
        validate_defaults(
            APPROVERS, [], cache=cache, user_lookup=counting,
            group_lookup=lambda n: {"name": n},
        )
        assert counter["n"] == first_calls

    def test_cache_miss_after_ttl_expiry(self):
        cache: dict = {}
        now_box = {"v": 1000.0}

        def now():
            return now_box["v"]

        validate_defaults(
            APPROVERS, [], cache=cache, user_lookup=_user_lookup_all_ok,
            group_lookup=lambda n: {"name": n}, now=now,
        )
        now_box["v"] += _CACHE_TTL_SECONDS + 1
        counter = {"n": 0}

        def counting(aid):
            counter["n"] += 1
            return {"accountId": aid}

        validate_defaults(
            APPROVERS, [], cache=cache, user_lookup=counting,
            group_lookup=lambda n: {"name": n}, now=now,
        )
        assert counter["n"] > 0

    def test_all_ok_property(self):
        result = ValidationResult(
            approvers=[ApproverCheck(account_id="a", ok=True)],
            groups=[GroupCheck(name="g", ok=True)],
        )
        assert result.all_ok
        result2 = ValidationResult(
            approvers=[ApproverCheck(account_id="a", ok=False, error="bad")],
        )
        assert not result2.all_ok

    def test_clear_cache(self):
        cache: dict = {"irrelevant": 1}
        validate_defaults(
            APPROVERS, [], cache=cache, user_lookup=_user_lookup_all_ok,
            group_lookup=lambda n: {"name": n},
        )
        clear_cache(cache)
        assert not any(isinstance(v, ValidationResult) for v in cache.values())
        assert "irrelevant" in cache

    def test_to_dict_roundtrip(self):
        result = validate_defaults(
            APPROVERS, [], user_lookup=_user_lookup_all_ok,
            group_lookup=lambda n: {"name": n},
        )
        d = result.to_dict()
        assert d["all_ok"] is True
        assert len(d["approvers"]) == 2
