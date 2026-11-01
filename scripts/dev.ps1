$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$python = if (Test-Path .venv\Scripts\python.exe) { (Resolve-Path .venv\Scripts\python.exe).Path } else { 'python' }
$packageManager = if (Get-Command npm -ErrorAction SilentlyContinue) { 'npm' } elseif (Get-Command pnpm -ErrorAction SilentlyContinue) { 'pnpm' } else { throw '未找到 npm 或 pnpm，请安装 Node.js。' }
$backend = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000' -PassThru
try { if ($packageManager -eq 'pnpm') { Push-Location (Join-Path $ProjectRoot 'frontend'); try { & pnpm dev } finally { Pop-Location } } else { & npm --prefix frontend run dev } } finally { if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force } }
