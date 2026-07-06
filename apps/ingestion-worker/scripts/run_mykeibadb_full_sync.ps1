<#
.SYNOPSIS
    Full mykeibadb sync (mykeibadb.exe -> batch.py).

.DESCRIPTION
    1. Run mykeibadb.exe to refresh the local MySQL (mykeibadb) via JV-Link,
       using the mykeibadb.ini already configured through wmykeibadb.exe.
       Waits with a timeout so an unattended run doesn't hang forever if
       "pause on exit" is left enabled in wmykeibadb.exe.
    2. batch.py --mode mykeibadb --step entries   -> pushes entries to PostgreSQL.
    3. batch.py --mode mykeibadb --step results   -> pushes confirmed results.

    Intended to be run from Windows Task Scheduler on a JRA-calendar-aware
    schedule (Fri/Sat 10:00, Sun 18:00 -- see setup_task_scheduler.ps1).
    mykeibadb.exe only fetches the delta since its last FROMTIME watermark,
    so re-runs are cheap even if triggered more often.

    Entries for upcoming races (special/final registration) are published
    ahead of race day, so the date window is not just "today" -- it queries
    a fixed range of "N days back" through "M days forward" (batch.py's
    default --date is a single day, so an explicit range must be passed).

.PARAMETER TimeoutSeconds
    Max seconds to wait for mykeibadb.exe (default 600 = 10 min).
    If "pause on exit" is left enabled in wmykeibadb.exe, this will time out
    and the process gets killed.

.PARAMETER DaysBack
    Start of the query window, days before today (default 7).

.PARAMETER DaysForward
    End of the query window, days after today (default 14).

.EXAMPLE
    .\run_mykeibadb_full_sync.ps1
#>
param(
    [int]$TimeoutSeconds = 600,
    [int]$DaysBack = 7,
    [int]$DaysForward = 14
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$WorkerDir = Split-Path $PSScriptRoot -Parent
$LogDir    = Join-Path $WorkerDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir "$(Get-Date -Format 'yyyyMMdd')-mykeibadb-sync.log"
$EnvFile = Join-Path $WorkerDir ".env"

function Write-Log {
    param([string]$Msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# --- Load .env (expands MYKEIBADB_EXE_PATH etc. into process env vars) ---
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^\s*([^#=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

$MykeibadbExe = [System.Environment]::GetEnvironmentVariable("MYKEIBADB_EXE_PATH", "Process")

Write-Log "=== run_mykeibadb_full_sync.ps1 start ==="

if (-not $MykeibadbExe -or -not (Test-Path $MykeibadbExe)) {
    Write-Log "ERROR: MYKEIBADB_EXE_PATH is not set, or mykeibadb.exe was not found: $MykeibadbExe"
    Write-Log "Fix: set MYKEIBADB_EXE_PATH=C:\...\mykeibadb.exe in .env"
    exit 1
}
$MykeibadbDir = Split-Path $MykeibadbExe -Parent

# --- Step 1: mykeibadb.exe (JV-Link -> local MySQL) ---
Write-Log "Starting mykeibadb.exe (waiting up to ${TimeoutSeconds}s): $MykeibadbExe"
$proc = Start-Process -FilePath $MykeibadbExe -WorkingDirectory $MykeibadbDir -WindowStyle Minimized -PassThru
$completed = $proc.WaitForExit($TimeoutSeconds * 1000)

if (-not $completed) {
    Write-Log "ERROR: mykeibadb.exe timed out. Killing the process."
    Write-Log "Fix: open wmykeibadb.exe and uncheck 'pause on exit' (shuuryouji ichiji teishi)."
    try { $proc.Kill() } catch {}
    exit 1
}
if ($proc.ExitCode -ne 0) {
    Write-Log "WARNING: mykeibadb.exe exited with a non-zero code: $($proc.ExitCode)"
} else {
    Write-Log "mykeibadb.exe finished (exit code 0)"
}

# --- Step 2/3: batch.py (local MySQL -> PostgreSQL) ---
$RunBatch = Join-Path $PSScriptRoot "run_batch.ps1"
$DateFrom = (Get-Date).AddDays(-$DaysBack).ToString("yyyyMMdd")
$DateTo   = (Get-Date).AddDays($DaysForward).ToString("yyyyMMdd")

Write-Log "--- entries sync (batch.py --mode mykeibadb --step entries, $DateFrom to $DateTo) ---"
& $RunBatch -Step entries -Mode mykeibadb -Date $DateFrom -DateTo $DateTo
$entriesExit = $LASTEXITCODE

Write-Log "--- results sync (batch.py --mode mykeibadb --step results, $DateFrom to $DateTo) ---"
& $RunBatch -Step results -Mode mykeibadb -Date $DateFrom -DateTo $DateTo
$resultsExit = $LASTEXITCODE

Write-Log "=== run_mykeibadb_full_sync.ps1 end (entries=$entriesExit results=$resultsExit) ==="

if ($entriesExit -ne 0 -or $resultsExit -ne 0) {
    exit 1
}
exit 0
