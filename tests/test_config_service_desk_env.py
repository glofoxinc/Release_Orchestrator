"""Tests for env-var override of service desk IDs."""

from __future__ import annotations

import importlib
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")


class TestServiceDeskEnvOverride:
    def test_env_overrides_yaml_for_service_desk_id(self):
        with patch.dict(os.environ, {"TCKT_SERVICE_DESK_ID": "env-desk-99"}, clear=False):
            import config
            importlib.reload(config)
            assert config.TCKT_SERVICE_DESK_ID == "env-desk-99"
        import config
        importlib.reload(config)

    def test_env_overrides_yaml_for_request_type_id(self):
        with patch.dict(os.environ, {"TCKT_REQUEST_TYPE_ID": "env-type-42"}, clear=False):
            import config
            importlib.reload(config)
            assert config.TCKT_REQUEST_TYPE_ID == "env-type-42"
        import config
        importlib.reload(config)

    def test_service_desk_request_type_configured(self):
        import config
        with patch.object(config, "TCKT_SERVICE_DESK_ID", "1"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "2"):
            assert config.service_desk_request_type_configured() is True
        with patch.object(config, "TCKT_SERVICE_DESK_ID", ""), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "2"):
            assert config.service_desk_request_type_configured() is False
