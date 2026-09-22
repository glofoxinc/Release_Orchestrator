"""Shared step navigation for Service Ticket — always persist before rerun."""

from __future__ import annotations

import streamlit as st

from session_persist import persist_session


def go_step(step: int) -> None:
    persist_session(dict(st.session_state))
    st.session_state["stk_step"] = step
    st.rerun()
