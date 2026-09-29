"""Root shim — Streamlit entry (UI lives under ``release_platform/``).

Run:
    streamlit run orchestrator/entry/app.py
    streamlit run release_platform/app.py
"""

from release_platform.app import *  # noqa: F403
