@echo off
if exist "%~dp0python-portable\python.exe" (
    start "" "%~dp0python-portable\python.exe" "%~dp0app.py"
) else (
    echo Portable Python not found. Please run setup_portable.py first.
    pause
)
