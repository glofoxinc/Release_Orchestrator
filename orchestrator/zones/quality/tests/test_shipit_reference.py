"""Tests for shipit_reference module."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import shipit_reference


def test_deployment_jql_targets_shipit():
    assert "project = SHIPIT" in shipit_reference._DEPLOYMENT_JQL
    assert "Insights Customize BI" in shipit_reference._DEPLOYMENT_JQL


def test_default_reference_key():
    assert shipit_reference.DEFAULT_REFERENCE_KEY == "SHIPIT-17036"


def test_gold_standard_keys_include_17191():
    assert "SHIPIT-17191" in shipit_reference.GOLD_STANDARD_KEYS
    assert "SHIPIT-17036" in shipit_reference.GOLD_STANDARD_KEYS


def test_build_shipit_summary():
    summary = shipit_reference.build_shipit_summary(version_name="v2026.3.09.09")
    assert summary == (
        "Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.09"
    )


def test_collect_approver_group_options_includes_defaults():
    groups = shipit_reference.collect_approver_group_options([])
    assert "Insights Customize Approvers" in groups
