@echo off
title Release Deployer - Setup
echo ============================================
echo   Release Deployer - One-Time Setup
echo ============================================
echo.

cd /d "%~dp0\..\..\..\..\.."

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/3] Virtual environment already exists.
)

echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r orchestrator\zones\config\deps\requirements.txt --quiet
pip install -e . --quiet
echo       Done.

set "ENV_DST=orchestrator\zones\runtime\local\.env"
set "ENV_SRC=orchestrator\zones\runtime\local\.env.example"
if not exist "%ENV_DST%" (
    echo [3/3] Creating .env from template...
    copy "%ENV_SRC%" "%ENV_DST%" >nul
) else (
    echo [3/3] .env already exists, skipping.
)

echo.
echo   Setup complete. Guide: orchestrator\zones\knowledge\guides\GUIDE.md
echo   MCP: python -m release_mcp
echo   UI:  streamlit run orchestrator\entry\app.py
pause
