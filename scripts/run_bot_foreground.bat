@echo off
:: SPK Mobile Bot - Run in foreground (see errors in console)
:: Use this to debug why the bot doesn't respond on desktop.
:: Run from project root:  scripts\run_bot_foreground.bat

cd /d "%~dp0\.."

:: Windows cp949 대신 UTF-8 사용 (이모지 오류 방지)
set "PYTHONIOENCODING=utf-8"

if exist "venv\Scripts\python.exe" (
    echo [*] Using venv. Starting bot in foreground...
    "venv\Scripts\python.exe" -m src.main
) else (
    echo [*] No venv. Using system Python...
    python -m src.main
)

echo.
echo [*] Bot exited. Press any key to close.
pause >nul
