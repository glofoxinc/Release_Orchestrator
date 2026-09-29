"""Native desktop launcher for Release Deployer.

Double-click this file to launch the app in a native OS window (no browser).
The .pyw extension runs without a visible console on Windows.
"""

import os
import subprocess
import sys
import time
import urllib.request

import socket

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = "127.0.0.1"
_PREFERRED_PORTS = [8501, 8502, 8503, 8504, 8505]


def _find_free_port():
    for p in _PREFERRED_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, p))
                return p
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


PORT = _find_free_port()
URL = f"http://{HOST}:{PORT}"

VENV_PYTHON = os.path.join(APP_DIR, ".venv", "Scripts", "pythonw.exe")
VENV_STREAMLIT = os.path.join(APP_DIR, ".venv", "Scripts", "streamlit.exe")


def _find_python():
    if os.path.exists(VENV_PYTHON):
        return VENV_PYTHON
    return sys.executable


def _find_streamlit():
    if os.path.exists(VENV_STREAMLIT):
        return VENV_STREAMLIT
    return "streamlit"


def _wait_for_server(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    streamlit_cmd = _find_streamlit()
    python_cmd = _find_python()

    env = os.environ.copy()
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_SERVER_PORT"] = str(PORT)
    env["STREAMLIT_SERVER_ADDRESS"] = HOST
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

    if streamlit_cmd.endswith(".exe"):
        cmd = [streamlit_cmd, "run", os.path.join(APP_DIR, "app.py")]
    else:
        cmd = [python_cmd, "-m", "streamlit", "run", os.path.join(APP_DIR, "app.py")]

    proc = subprocess.Popen(
        cmd,
        cwd=APP_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    try:
        if not _wait_for_server():
            proc.kill()
            return

        import webview
        window = webview.create_window(
            "Release Deployer",
            URL,
            width=1280,
            height=860,
            min_size=(900, 600),
        )
        webview.start()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
