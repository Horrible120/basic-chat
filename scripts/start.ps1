$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$packageManager = if (Get-Command npm -ErrorAction SilentlyContinue) { 'npm' } elseif (Get-Command pnpm -ErrorAction SilentlyContinue) { 'pnpm' } else { throw '未找到 npm 或 pnpm，请安装 Node.js。' }
if ($packageManager -eq 'pnpm') { Push-Location (Join-Path $ProjectRoot 'frontend'); try { & pnpm build } finally { Pop-Location } } else { & npm --prefix frontend run build }
$python = if (Test-Path .venv\Scripts\python.exe) { (Resolve-Path .venv\Scripts\python.exe).Path } else { 'python' }
& $python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
