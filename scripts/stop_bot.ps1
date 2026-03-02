# PowerShell에서 .\scripts\stop_bot.bat 오류 시 사용
# 사용법: .\scripts\stop_bot.ps1
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
cmd /c "scripts\stop_bot.bat"
