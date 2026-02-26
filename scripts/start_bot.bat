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

:: Start in background (pythonw = no console window)
echo [*] Starting SPK Mobile Bot in background...
start "" /B pythonw.exe -m src.main

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
