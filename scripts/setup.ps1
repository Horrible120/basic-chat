$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw '未找到 Python，请安装 Python 3.11+。' }
$pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$pythonVersion -lt [version]'3.11') { throw "Python 版本过低：$pythonVersion" }
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue) -and -not (Get-Command npm -ErrorAction SilentlyContinue)) { throw '未找到 npm 或 pnpm，请安装 Node.js。' }

if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv --without-pip .venv }
$venvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
& $venvPython -m ensurepip --upgrade 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning '虚拟环境缺少 ensurepip，将使用系统 Python 安装后端依赖。'; $venvPython = (Get-Command python).Source }
& $venvPython -m pip install -r backend/requirements-dev.txt
if (Get-Command npm -ErrorAction SilentlyContinue) {
    npm --prefix frontend install
} elseif (Get-Command pnpm -ErrorAction SilentlyContinue) {
    Push-Location (Join-Path $ProjectRoot 'frontend')
    try { pnpm install } finally { Pop-Location }
} else { throw '未找到 npm 或 pnpm，请安装 Node.js。' }
Write-Host '依赖安装完成。'
