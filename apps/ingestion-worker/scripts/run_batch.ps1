<#
.SYNOPSIS
    Ingestion batch runner wrapper (retry + failure notification).

.DESCRIPTION
    Invoked from Windows Task Scheduler.
    Retries the given step up to $MaxRetries times; notifies NOTIFY_WEBHOOK_URL on
    final failure. Logs are written per-date under logs\.

.PARAMETER Step
    Step to run: all | masters | entries | results | special-entries

.PARAMETER Mode
    Data source: jvlink | fixture | mykeibadb (default: jvlink)

.PARAMETER Date
    Start date YYYYMMDD (default: today)

.PARAMETER DateTo
    End date YYYYMMDD (optional). When omitted, --date-to is not passed and
    batch.py treats it as the same as Date.

.PARAMETER MaxRetries
    Max retry attempts (default: 3)

.EXAMPLE
    .\run_batch.ps1 -Step entries
    .\run_batch.ps1 -Step results -Date 20260628
    .\run_batch.ps1 -Step entries -Mode mykeibadb -Date 20260629 -DateTo 20260720
#>
param(
    [Parameter(Mandatory)][string]$Step,
    [string]$Mode = "jvlink",
    [string]$Date = (Get-Date -Format "yyyyMMdd"),
    [string]$DateTo = "",
    [int]$MaxRetries = 3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

$rangeLabel = if ($DateTo) { "$Date to $DateTo" } else { $Date }
Write-Log "=== run_batch.ps1 start: step=$Step mode=$Mode date=$rangeLabel ==="

$batchArgs = @("-m", "ingestion.batch", "--mode", $Mode, "--step", $Step, "--date", $Date)
if ($DateTo) { $batchArgs += @("--date-to", $DateTo) }

$attempt = 0
$success = $false

while ($attempt -lt $MaxRetries -and -not $success) {
    $attempt++
    Write-Log "attempt $attempt/$MaxRetries"

    try {
        & $Python @batchArgs 2>&1 |
            Tee-Object -FilePath $LogFile -Append
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

    # Slack-compatible webhook notification
    $webhookUrl = [System.Environment]::GetEnvironmentVariable("NOTIFY_WEBHOOK_URL", "Process")
    if ($webhookUrl) {
        try {
            $body = @{ text = ":x: *ingestion-worker failed*`n- step: ``$Step```n- date: ``$Date```n- see log: $LogFile" } |
                ConvertTo-Json -Compress
            Invoke-RestMethod -Uri $webhookUrl -Method Post -Body $body -ContentType "application/json"
            Write-Log "failure notification sent"
        } catch {
            Write-Log "failed to send notification: $_"
        }
    }

    exit 1
}

Write-Log "=== run_batch.ps1 end ==="
exit 0
