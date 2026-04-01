@echo off
title Reddit Discussion Explorer

echo ==========================================
echo   Reddit Discussion Explorer - Launcher
echo ==========================================
echo.

:: Check Python
py --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

:: Check for virtual environment
if not exist "venv" (
    echo [INFO] Creating virtual environment...
    py -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install dependencies
echo [INFO] Installing dependencies...
py -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Check for .env
if not exist ".env" (
    echo.
    echo [WARNING] No .env file found!
    echo Please copy .env.example to .env and fill in your Reddit API credentials.
    echo.
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [INFO] Copied .env.example to .env - please edit it with your credentials.
        echo.
    )
    pause
)

echo.
echo [INFO] Starting server...
echo [INFO] Opening browser at http://localhost:5000
echo.

:: Open browser after a short delay
start "" /min cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5000"

:: Start the server
py server.py

pause