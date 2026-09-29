"""Drift gate and scope-restore gate behavior."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")


@pytest.fixture
def mock_streamlit():
    ss: dict = {}
    with patch("ui.helpers.st") as mock_st:
        mock_st.session_state = ss
        mock_st.button = MagicMock(return_value=False)
        mock_st.columns = MagicMock(return_value=[MagicMock(), MagicMock()])
        mock_st.error = MagicMock()
        mock_st.markdown = MagicMock()
        mock_st.rerun = MagicMock()
        yield mock_st, ss


class TestScopeRestoreGate:
    def test_blocks_when_scope_restore_flag_set(self, mock_streamlit):
        from release_platform.ui.helpers import render_scope_restore_gate

        mock_st, ss = mock_streamlit
        ss["_scope_restore_blocked"] = True
        ss["_scope_restore_changed"] = ["PIC", "AN"]

        assert render_scope_restore_gate("rn") is False

    def test_acknowledge_clears_block(self, mock_streamlit):
        from release_platform.ui.helpers import render_scope_restore_gate

        mock_st, ss = mock_streamlit
        ss["_scope_restore_blocked"] = True
        ss["_scope_restore_changed"] = ["PIC"]

        def _button(label, **kwargs):
            return kwargs.get("key") == "rn_scope_ack"

        mock_st.button = MagicMock(side_effect=_button)

        assert render_scope_restore_gate("rn") is True
        assert "_scope_restore_blocked" not in ss


class TestContinueWithDriftGate:
    def test_not_clicked_returns_false(self, mock_streamlit):
        from release_platform.ui.helpers import continue_with_drift_gate

        mock_st, ss = mock_streamlit
        assert continue_with_drift_gate("rn", clicked=False) is False

    def test_clicked_with_ok_drift_proceeds(self, mock_streamlit):
        from release_platform.ui.helpers import continue_with_drift_gate

        mock_st, ss = mock_streamlit
        with patch("ui.helpers.check_snapshot_drift", return_value={"status": "ok"}):
            with patch("ui.helpers.render_scope_restore_gate", return_value=True):
                assert continue_with_drift_gate("rn", clicked=True) is True
        assert "_rn_continue_pending" not in ss

    def test_scope_block_prevents_proceed(self, mock_streamlit):
        from release_platform.ui.helpers import continue_with_drift_gate

        mock_st, ss = mock_streamlit
        with patch("ui.helpers.render_scope_restore_gate", return_value=False):
            assert continue_with_drift_gate("stk", clicked=True) is False
        assert ss.get("_stk_continue_pending") is True
