@echo off
:: SPK Mobile Bot - Status Check

:: Move to the repository root directory
cd /d "%~dp0\.."

echo ==================================================
echo    SPK MOBILE BOT - SERVICE STATUS
echo ==================================================
echo.

:: Check PID file
if not exist spk_bot.pid (
    echo   Status:  STOPPED (no PID file)
    goto :log
)

set /p PID=<spk_bot.pid
tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul
if not errorlevel 1 (
    echo   Status:  RUNNING
    echo   PID:     %PID%
) else (
    echo   Status:  STOPPED (stale PID file)
    del spk_bot.pid 2>nul
)

:log
echo.

:: Show recent log entries
if exist spk_bot.log (
    echo --- Last 15 Log Lines ---
    powershell -Command "Get-Content '%cd%\spk_bot.log' -Tail 15"
) else (
    echo   No log file found.
)

echo.
echo ==================================================
pause
