$ErrorActionPreference = 'Stop'
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) { throw '未找到 cloudflared，请先安装并加入 PATH。' }
try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 3 | Out-Null } catch { throw '后端未运行，请先执行 .\scripts\start.ps1。' }
cloudflared tunnel --url http://127.0.0.1:8000
