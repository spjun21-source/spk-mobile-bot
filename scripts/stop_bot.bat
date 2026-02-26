@echo off
:: SPK Mobile Bot - Stop Script

:: Move to the repository root directory
cd /d "%~dp0\.."

if not exist spk_bot.pid (
    echo [i] Bot is not running (no PID file found).
    :: Also check for any stray processes
    for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq pythonw.exe" /FO LIST 2^>nul ^| findstr "PID"') do (
        echo [?] Found pythonw.exe process PID: %%i
        echo     If this is the bot, run: taskkill /PID %%i /F
    )
    pause
    exit /b 0
)

set /p PID=<spk_bot.pid
echo [*] Stopping bot (PID: %PID%)...
taskkill /PID %PID% /F >nul 2>&1

if not errorlevel 1 (
    echo [OK] Bot stopped.
    del spk_bot.pid 2>nul
) else (
    echo [!] Could not stop process %PID% (may have already exited).
    del spk_bot.pid 2>nul
)
echo.
pause
