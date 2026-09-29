@echo off
title Release Deployer - Setup
echo ============================================
echo   Release Deployer - One-Time Setup
echo ============================================
echo.

cd /d "%~dp0"

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Create virtual environment
if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
    echo       Done.
) else (
    echo [1/3] Virtual environment already exists.
)

:: Activate and install dependencies
echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
echo       Done.

:: Copy .env.example to .env if needed
if not exist ".env" (
    echo [3/3] Creating .env from template...
    copy .env.example .env >nul
    echo       Done.
    echo.
    echo  !! IMPORTANT: Open .env and add your Jira email and API token.
    echo     Or just launch the app -- it will ask you on first run.
) else (
    echo [3/3] .env already exists, skipping.
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo   Project folder: %~dp0
echo   Launch:         .venv\Scripts\streamlit run app.py --server.port 8501
echo   New user guide: docs\SETUP.md
echo.
echo   To launch (native window):  double-click launcher.pyw
echo   To launch (browser):        double-click launch.vbs
echo.
pause
