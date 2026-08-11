@echo off
setlocal
cd /d "%~dp0backend"

if not exist "venv\Scripts\python.exe" (
    echo Backend venv not found. Run setup.ps1 first ^(right-click it, "Run with PowerShell"^).
    pause
    exit /b 1
)

venv\Scripts\python.exe run.py
