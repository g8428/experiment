# Deepcoin bot auto-start (run by Task Scheduler task 'DeepcoinBot' at Windows logon).
# ASCII only: Windows PowerShell 5.1 misreads UTF-8 (no BOM) Korean text and fails to parse.
# - If a server is already listening on port 5000, do nothing (no duplicate run).
# - Start server.py as an independent process (survives closing the Claude app),
#   then start the real-mode bots for tuning.json active_symbols.
# - Log: trade_logs/autostart.log
$ErrorActionPreference = 'Continue'
$dir = $PSScriptRoot
$log = Join-Path $dir 'trade_logs\autostart.log'
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Out-File -FilePath $log -Append -Encoding utf8 }

if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) {
    Log 'already running - skip'
    exit 0
}

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = Join-Path $env:USERPROFILE 'anaconda3\python.exe' }
$cmd = "cmd.exe /c `"`"$py`" -u server.py > trade_logs\server_stdout.log 2> trade_logs\server_stderr.log`""
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $dir }
Log "server start requested ReturnValue=$($r.ReturnValue) PID=$($r.ProcessId)"

$up = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 3
    try { Invoke-RestMethod -Uri 'http://localhost:5000/api/bots/status' -TimeoutSec 3 | Out-Null; $up = $true; break } catch {}
}
if (-not $up) { Log 'server did not respond - bots not started'; exit 1 }

try {
    $body = @{ mode = 'real' } | ConvertTo-Json
    $res = Invoke-RestMethod -Uri 'http://localhost:5000/api/claude/start' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 10
    Log "bots started: $($res.syms -join ', ') / skipped: $($res.skipped_not_active -join ', ')"
} catch {
    Log "bot start failed: $_"
    exit 1
}
