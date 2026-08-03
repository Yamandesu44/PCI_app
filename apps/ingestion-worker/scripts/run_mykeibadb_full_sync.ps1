<#
.SYNOPSIS
    Full mykeibadb sync (mykeibadb.exe -> batch.py).

.DESCRIPTION
    1. Run mykeibadb.exe to refresh the local MySQL (mykeibadb) via JV-Link,
       using the mykeibadb.ini already configured through wmykeibadb.exe.
       Waits with a timeout so an unattended run doesn't hang forever if
       "pause on exit" is left enabled in wmykeibadb.exe.
    2. batch.py --mode mykeibadb --step entries          -> pushes entries to PostgreSQL.
    3. batch.py --mode mykeibadb --step race-metadata     -> backfills track condition/weather.
    4. batch.py --mode mykeibadb --step results           -> pushes confirmed results.
    5. batch.py --mode mykeibadb --step special-entries  -> pushes graded-stakes advance
       entries (TOKUBETSU_TOROKUBA/TOKUBETSU_TOROKUBAGOTO_JOHO tables) for next week's races.
       This reads a different mykeibadb table than step 2, so it was silently never run
       by this script until 2026-07-13 -- see docs/DECISIONS.md.
    6. batch.py --step forecasts -> precomputes upcoming forecasts after all entry updates.

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
    Start of the query window, days before today (default 10).
    10 (not 7) so that a single skipped weekend does not silently drop the
    prior weekend's confirmed results out of the window: running on a Monday
    with DaysBack=7 starts at the previous Tuesday and excludes the Saturday
    8 days earlier. For a longer backfill pass an explicit larger value, e.g.
    .\run_mykeibadb_full_sync.ps1 -DaysBack 21

.PARAMETER DaysForward
    End of the query window, days after today (default 14).

.PARAMETER PreflightOnly
    Check whether the API and PostgreSQL are ready, then exit without
    running mykeibadb.exe or any ingestion steps.

.PARAMETER ApiBaseUrl
    事前疎通と全取り込み工程のAPI_BASE_URLを上書きする。

.EXAMPLE
    .\run_mykeibadb_full_sync.ps1

.EXAMPLE
    .\run_mykeibadb_full_sync.ps1 -PreflightOnly

.EXAMPLE
    .\run_mykeibadb_full_sync.ps1 -ApiBaseUrl http://127.0.0.1:8998
#>
param(
    [int]$TimeoutSeconds = 600,
    [int]$DaysBack = 10,
    [int]$DaysForward = 14,
    [string]$ApiBaseUrl = "",
    [switch]$PreflightOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1でも、直接呼び出すPython疎通チェックをUTF-8として扱う。
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

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

function Test-IngestApiReadiness {
    param(
        [Parameter(Mandatory)][string]$BaseUrl,
        [int]$TimeoutSeconds = 15
    )

    $readyUrl = "$($BaseUrl.TrimEnd('/'))/ready"
    Write-Log "Preflight: checking API and PostgreSQL readiness: $readyUrl"

    try {
        $response = Invoke-RestMethod -Uri $readyUrl -Method Get -TimeoutSec $TimeoutSeconds
        if ($response.status -eq "ready" -and $response.database -eq "ok") {
            Write-Log "Preflight OK: API and PostgreSQL are ready."
            return $true
        }

        Write-Log "ERROR: readiness check returned status=$($response.status) database=$($response.database)"
        if ($response.message) { Write-Log "Detail: $($response.message)" }
        if ($response.action) { Write-Log "Action: $($response.action)" }
    } catch {
        Write-Log "ERROR: API or PostgreSQL is not ready: $($_.Exception.Message)"
    }

    Write-Log "Fix 1: start Docker Desktop."
    Write-Log "Fix 2: from the repository root, run: docker compose up -d db"
    Write-Log "Fix 3: from apps\api, run: .venv\Scripts\python.exe -m alembic upgrade head"
    Write-Log "Fix 4: restart FastAPI, then confirm: http://localhost:8000/ready"
    return $false
}

function Test-MykeibadbReadiness {
    # 読み取り元(MySQL)が落ちていると、mykeibadb.exe は何もできないまま exit 0 を返し、
    # batch.py がリトライを繰り返した末に接続拒否で落ちる。ここで先に止める。
    param([Parameter(Mandatory)][string]$PythonExe)

    Write-Log "Preflight: checking source mykeibadb (MySQL) connectivity"
    # run_batch.ps1 と同じ理由: 2>&1 で拾った stderr を PowerShell が終了エラーに
    # しないよう、この呼び出しの間だけ Continue へ落とす。
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $PythonExe -m ingestion.check_mykeibadb 2>&1 | ForEach-Object {
            Write-Log $_.ToString()
        }
    } finally {
        $ErrorActionPreference = $prevEAP
    }
    if ($LASTEXITCODE -eq 0) { return $true }

    Write-Log "Sync aborted: the source database is unreachable."
    return $false
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
if (-not $ApiBaseUrl) {
    $ApiBaseUrl = [System.Environment]::GetEnvironmentVariable("API_BASE_URL", "Process")
}
if (-not $ApiBaseUrl) { $ApiBaseUrl = "http://localhost:8000" }
$parsedApiUrl = $null
if (-not [Uri]::TryCreate($ApiBaseUrl, [UriKind]::Absolute, [ref]$parsedApiUrl) -or
    $parsedApiUrl.Scheme -notin @("http", "https") -or
    $parsedApiUrl.UserInfo) {
    throw "-ApiBaseUrlには認証情報を含まないHTTP(S) URLを指定してください。"
}
$ApiBaseUrl = $ApiBaseUrl.TrimEnd("/")
$env:API_BASE_URL = $ApiBaseUrl

Write-Log "=== run_mykeibadb_full_sync.ps1 start ==="

if (-not (Test-IngestApiReadiness -BaseUrl $ApiBaseUrl)) {
    Write-Log "Sync aborted before mykeibadb.exe was started."
    exit 1
}

$Venv = Join-Path $WorkerDir ".venv\Scripts\python.exe"
$Python = if (Test-Path $Venv) { $Venv } else { "python" }

if (-not (Test-MykeibadbReadiness -PythonExe $Python)) {
    Write-Log "Sync aborted before mykeibadb.exe was started."
    exit 1
}

if ($PreflightOnly) {
    Write-Log "Preflight-only check completed."
    exit 0
}

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

# --- Step 2-6: batch.py (local MySQL -> PostgreSQL -> forecast mart) ---
$RunBatch = Join-Path $PSScriptRoot "run_batch.ps1"
$DateFrom = (Get-Date).AddDays(-$DaysBack).ToString("yyyyMMdd")
$DateTo   = (Get-Date).AddDays($DaysForward).ToString("yyyyMMdd")

Write-Log "--- entries sync (batch.py --mode mykeibadb --step entries, $DateFrom to $DateTo) ---"
& $RunBatch -Step entries -Mode mykeibadb -Date $DateFrom -DateTo $DateTo -ApiBaseUrl $ApiBaseUrl
$entriesExit = $LASTEXITCODE

Write-Log "--- race-metadata sync (batch.py --mode mykeibadb --step race-metadata, $DateFrom to $DateTo) ---"
& $RunBatch -Step race-metadata -Mode mykeibadb -Date $DateFrom -DateTo $DateTo -ApiBaseUrl $ApiBaseUrl
$metadataExit = $LASTEXITCODE

Write-Log "--- results sync (batch.py --mode mykeibadb --step results, $DateFrom to $DateTo) ---"
& $RunBatch -Step results -Mode mykeibadb -Date $DateFrom -DateTo $DateTo -ApiBaseUrl $ApiBaseUrl
$resultsExit = $LASTEXITCODE

Write-Log "--- special-entries sync (batch.py --mode mykeibadb --step special-entries, $DateFrom to $DateTo) ---"
& $RunBatch -Step special-entries -Mode mykeibadb -Date $DateFrom -DateTo $DateTo -ApiBaseUrl $ApiBaseUrl
$specialEntriesExit = $LASTEXITCODE

Write-Log "--- forecast precompute (batch.py --step forecasts, $DateFrom to $DateTo) ---"
& $RunBatch -Step forecasts -Mode mykeibadb -Date $DateFrom -DateTo $DateTo -ApiBaseUrl $ApiBaseUrl
$forecastsExit = $LASTEXITCODE

Write-Log "=== run_mykeibadb_full_sync.ps1 end (entries=$entriesExit race-metadata=$metadataExit results=$resultsExit special-entries=$specialEntriesExit forecasts=$forecastsExit) ==="

if ($entriesExit -ne 0 -or $metadataExit -ne 0 -or $resultsExit -ne 0 -or $specialEntriesExit -ne 0 -or $forecastsExit -ne 0) {
    exit 1
}
exit 0
