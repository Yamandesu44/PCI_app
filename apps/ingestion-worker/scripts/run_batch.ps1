<#
.SYNOPSIS
    Ingestion batch runner wrapper (retry + failure notification).

.DESCRIPTION
    Invoked from Windows Task Scheduler.
    Retries the given step up to $MaxRetries times; notifies NOTIFY_WEBHOOK_URL on
    final failure. Logs are written per-date under logs\.

.PARAMETER Step
    Step to run: all | masters | entries | results | race-metadata |
    special-entries | forecasts

.PARAMETER Mode
    Data source: jvlink | fixture | mykeibadb (default: jvlink)

.PARAMETER Date
    Start date YYYYMMDD (default: today)

.PARAMETER DateTo
    End date YYYYMMDD (optional). When omitted, --date-to is not passed and
    batch.py treats it as the same as Date.

.PARAMETER MaxRetries
    Max retry attempts (default: 3)

.PARAMETER ChunkDays
    Split long date ranges into chunks of this many days (default: 0 = disabled).

.PARAMETER TestNotification
    Send one harmless test notification and exit without running ingestion.

.EXAMPLE
    .\run_batch.ps1 -Step entries
    .\run_batch.ps1 -Step results -Date 20260628
    .\run_batch.ps1 -Step entries -Mode mykeibadb -Date 20260629 -DateTo 20260720
    .\run_batch.ps1 -Step race-metadata -Mode mykeibadb -Date 20250723 -DateTo 20260723 -ChunkDays 7
#>
param(
    [string]$Step = "",
    [string]$Mode = "jvlink",
    [string]$Date = (Get-Date -Format "yyyyMMdd"),
    [string]$DateTo = "",
    [int]$ChunkDays = 0,
    [int]$MaxRetries = 3,
    [switch]$TestNotification
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1でもPythonの日本語ログを同じUTF-8として扱う。
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

if ($TestNotification -and -not $Step) { $Step = "webhook-test" }
if (-not $Step) { throw "-Step is required." }

# --- Path resolution ---
$WorkerDir = Split-Path $PSScriptRoot -Parent
$LogDir    = Join-Path $WorkerDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$LogFile = Join-Path $LogDir "$Date-$Step.log"
$EnvFile = Join-Path $WorkerDir ".env"

# --- Resolve Python (prefer venv) ---
$Venv = Join-Path $WorkerDir ".venv\Scripts\python.exe"
$Python = if (Test-Path $Venv) { $Venv } else { "python" }

# --- Load .env (expands NOTIFY_WEBHOOK_URL etc. into process env vars) ---
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^\s*([^#=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

function Write-Log {
    param([string]$Msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Send-WebhookNotification {
    param(
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][string]$Message
    )

    try {
        # Windows PowerShell 5.1でもSlack等が要求するTLS 1.2を明示する。
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $body = @{ text = $Message } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri $Url -Method Post -Body $body `
            -ContentType "application/json" -TimeoutSec 10 | Out-Null
        Write-Log "webhook notification sent"
        return $true
    } catch {
        # Webhook URLには認証情報が含まれるため、例外内に含まれてもログへ残さない。
        $safeError = $_.Exception.Message.Replace($Url, "<redacted>")
        Write-Log "failed to send webhook notification: $safeError"
        return $false
    }
}

$rangeLabel = if ($DateTo) { "$Date to $DateTo" } else { $Date }
Write-Log "=== run_batch.ps1 start: step=$Step mode=$Mode date=$rangeLabel ==="

$webhookUrl = [System.Environment]::GetEnvironmentVariable("NOTIFY_WEBHOOK_URL", "Process")
if ($TestNotification) {
    if (-not $webhookUrl) {
        Write-Log "ERROR: NOTIFY_WEBHOOK_URL is not set."
        exit 1
    }
    $testMessage = ":white_check_mark: *PCI App notification test*`nWindows ingestion worker is connected."
    if (Send-WebhookNotification -Url $webhookUrl -Message $testMessage) { exit 0 }
    exit 1
}

$batchArgs = @("-m", "ingestion.batch", "--mode", $Mode, "--step", $Step, "--date", $Date)
if ($DateTo) { $batchArgs += @("--date-to", $DateTo) }
if ($ChunkDays -gt 0) { $batchArgs += @("--chunk-days", $ChunkDays) }

# 再試行中の重複通知を避け、最終失敗時の通知はこのラッパーが1回だけ送る。
$env:INGEST_NOTIFICATION_OWNER = "wrapper"

$attempt = 0
$success = $false

while ($attempt -lt $MaxRetries -and -not $success) {
    $attempt++
    Write-Log "attempt $attempt/$MaxRetries"

    try {
        # Pythonのloggingは既定でstderrへ出すため、この呼び出し中だけ
        # PowerShellが通常ログを終了エラーとして扱わないようにする。
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $Python @batchArgs 2>&1 | ForEach-Object {
                $line = $_.ToString()
                Write-Host $line
                Add-Content -Path $LogFile -Value $line -Encoding UTF8
            }
        } finally {
            $ErrorActionPreference = $prevEAP
        }
        if ($LASTEXITCODE -eq 0) {
            $success = $true
            Write-Log "done (attempt $attempt)"
        } else {
            Write-Log "failed exit=$LASTEXITCODE"
        }
    } catch {
        Write-Log "exception: $_"
    }

    if (-not $success -and $attempt -lt $MaxRetries) {
        $wait = 30 * $attempt
        Write-Log "waiting ${wait}s before retry..."
        Start-Sleep -Seconds $wait
    }
}

if (-not $success) {
    $errMsg = "$Step batch failed after $MaxRetries attempts (date=$Date)"
    Write-Log "ERROR: $errMsg"

    if ($webhookUrl) {
        $failureMessage = ":x: *ingestion-worker failed*`n- step: ``$Step```n- date: ``$Date```n- see log: $LogFile"
        Send-WebhookNotification -Url $webhookUrl -Message $failureMessage | Out-Null
    }

    exit 1
}

Write-Log "=== run_batch.ps1 end ==="
exit 0
