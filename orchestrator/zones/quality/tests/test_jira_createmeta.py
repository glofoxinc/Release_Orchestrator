"""Tests for Jira createmeta field parsing."""

from __future__ import annotations

import jira_client


def test_field_meta_from_createmeta_list_shape():
    data = {
        "fields": [
            {"fieldId": "assignee", "name": "Assignee"},
            {
                "fieldId": "customfield_11748",
                "key": "customfield_11748",
                "allowedValues": [
                    {"value": "Moderate / Limited", "id": "10820"},
                ],
            },
        ]
    }
    meta = jira_client._field_meta_from_createmeta(data, "customfield_11748")
    assert meta["fieldId"] == "customfield_11748"
    assert meta["allowedValues"][0]["id"] == "10820"


def test_field_meta_from_createmeta_dict_shape():
    data = {
        "fields": {
            "customfield_11748": {
                "allowedValues": [{"value": "Medium", "id": "1"}],
            }
        }
    }
    meta = jira_client._field_meta_from_createmeta(data, "customfield_11748")
    assert meta["allowedValues"][0]["id"] == "1"


def test_resolve_custom_field_option_with_list_createmeta(monkeypatch):
    jira_client._field_option_cache.clear()

    def fake_get(path, params=None):
        return {
            "fields": [
                {
                    "fieldId": "customfield_11748",
                    "allowedValues": [
                        {"value": "Moderate / Limited", "id": "10820"},
                    ],
                }
            ]
        }

    monkeypatch.setattr(jira_client, "_get", fake_get)
    resolved = jira_client.resolve_custom_field_option(
        "TCKT", "10502", "customfield_11748", "Moderate / Limited",
    )
    assert resolved == {"id": "10820"}
