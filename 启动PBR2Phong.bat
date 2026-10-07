@echo off
rem ---------------------------------------------------------------
rem  PBR2Phong launcher.
rem  Keep this file ASCII-only AND with CRLF line endings:
rem    - cmd.exe reads .bat with the OEM codepage, so UTF-8 Chinese
rem      gets mangled and then executed as commands;
rem    - LF-only line endings make cmd mis-parse rem/if blocks.
rem  Chinese guidance lives in the app and in the self-test checklist.
rem ---------------------------------------------------------------
cd /d "%~dp0PBR2Phong"

if not exist "gui\main.py" (
    echo Cannot find gui\main.py next to this launcher.
    echo Expected: %~dp0PBR2Phong\gui\main.py
    pause
    exit /b 1
)

python -m gui.main
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  Failed to start. Please check:
    echo    1^) Python 3.10+ installed  ^(try: python --version^)
    echo    2^) PySide6 installed       ^(try: pip install PySide6^)
    echo    3^) The error message above.
    echo ============================================================
    pause
)
