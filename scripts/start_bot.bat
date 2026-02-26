@echo off
:: SPK Mobile Bot - Background Start Script
:: Starts the bot as a hidden background process using pythonw.exe

:: Move to the repository root directory (one level up from scripts/)
cd /d "%~dp0\.."

:: Check if already running
if exist spk_bot.pid (
    set /p PID=<spk_bot.pid
    tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul
    if not errorlevel 1 (
        echo [!] Bot is already running (PID: %PID%)
        echo     Use scripts\stop_bot.bat to stop it first.
        pause
        exit /b 1
    ) else (
        echo [i] Stale PID file found. Cleaning up...
        del spk_bot.pid
    )
)

:: Use venv Python if present (desktop may not have system Python path)
set "PYEXE=pythonw.exe"
if exist "venv\Scripts\pythonw.exe" set "PYEXE=venv\Scripts\pythonw.exe"

:: Windows cp949 대신 UTF-8 사용 (이모지 오류 방지)
set "PYTHONIOENCODING=utf-8"

:: Start in background; log to spk_bot.log so we can see startup errors
echo [*] Starting SPK Mobile Bot in background...
start "" /B cmd /c ""%PYEXE%" -m src.main >> spk_bot.log 2>&1"

:: Wait a moment for PID file
timeout /t 2 /nobreak >nul

if exist spk_bot.pid (
    set /p PID=<spk_bot.pid
    echo [OK] Bot started successfully! (PID: %PID%)
    echo.
    echo     Log file: %cd%\spk_bot.log
    echo     Stop:     scripts\stop_bot.bat
    echo     Status:   scripts\status_bot.bat
) else (
    echo [OK] Bot process launched. Check spk_bot.log for details.
)
echo.
pause
