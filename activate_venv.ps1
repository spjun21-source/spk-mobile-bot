# SPK Mobile Bot - 가상환경 생성 및 활성화
# 사용법: . .\activate_venv.ps1  (앞의 점과 공백 필수)

$ProjectRoot = $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot "venv"
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"

if (-not (Test-Path $ActivateScript)) {
    Write-Host "[*] venv not found. Creating virtual environment..." -ForegroundColor Yellow
    # Windows에서는 py 런처가 더 안정적일 수 있음
    $pythonCmd = if ($IsWindows -ne $false -and (Get-Command py -ErrorAction SilentlyContinue)) { "py" } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
    & $pythonCmd -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create venv. Check that Python is installed (python or py in PATH)."
        return
    }
    Write-Host "[OK] venv created." -ForegroundColor Green
}

. $ActivateScript
Write-Host "[OK] Virtual environment activated." -ForegroundColor Green
