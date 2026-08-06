<#
.SYNOPSIS
    Register the mykeibadb sync task in Windows Task Scheduler.

.DESCRIPTION
    Run this as Administrator.
    Re-running overwrites any existing task with the same name.

    Registers:
      PaceLab_Sync_Mykeibadb
        Runs mykeibadb.exe (JV-Link -> local MySQL) then batch.py
        (MySQL -> PostgreSQL entries + results) end to end, via
        scripts\sync_mykeibadb.bat.

    Schedule:
      Tue 21:00  Special (graded stakes) entries announced Monday.
      Fri 10:00  Saturday and Sunday entries, post-position draw.
      Fri 21:00  Spare, in case the morning run failed.
      Sat 10:00  Fills in Sunday, if its draw only lands on Saturday.
      Sat 21:00  Saturday results.
      Sun 21:00  Sunday results.

    Why these times:
      Each run re-reads a rolling window (10 days back through the
      future), so a missed run is picked up by the next one. The
      schedule therefore controls how quickly data appears, not
      whether it arrives at all -- extra runs are cheap insurance.

      Saturday 21:00 is the one that matters most. Without it,
      Saturday's results only land on Sunday evening, leaving the
      board showing zero confirmed races for a full day -- across
      Saturday night and Sunday morning, when people are reviewing
      Saturday and handicapping Sunday.

      21:00 is a margin over the last race (confirmed around 16:30),
      not a measured figure. If the earlier 18:00 Sunday run was
      capturing every race, 18:00 is fine and worth keeping.

    Prerequisites:
      MYKEIBADB_EXE_PATH (full path to mykeibadb.exe) is set in .env.
      API_BASE_URL and INGEST_TOKEN in .env point at the deployed API.
      "Pause on exit" is unchecked in wmykeibadb.exe (otherwise an
      unattended run will hang waiting for a keypress).

.EXAMPLE
    # Open PowerShell as Administrator and run:
    powershell -ExecutionPolicy Bypass -File .\scripts\setup_task_scheduler.ps1

    # Calling the script directly fails on a default Windows install,
    # which blocks local scripts. Bypassing for this one call leaves the
    # machine's policy alone -- sync_mykeibadb.bat does the same thing.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskName = "PaceLab_Sync_Mykeibadb"
$LegacyTaskName = "PCI_Sync_Mykeibadb"

$WorkerDir = Split-Path $PSScriptRoot -Parent
$SyncBat = Join-Path $WorkerDir "scripts\sync_mykeibadb.bat"

if (-not (Test-Path $SyncBat)) {
    throw "Batch file not found: $SyncBat"
}

# The task used to be registered under the old product name. Leaving it in
# place would run the sync twice on every trigger, over the same window.
if (Get-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $LegacyTaskName -Confirm:$false
    Write-Host "Removed the old task: $LegacyTaskName"
}

# Run the task as the current logged-in user (no password needed, but only
# runs while that user is logged on). For a headless server, switch to
# -RunLevel Highest -User "SYSTEM" instead.
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

$Triggers = @(
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday  -At "21:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday   -At "10:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday   -At "21:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At "10:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At "21:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday   -At "21:00"
)

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$SyncBat`""

# Every setting here exists to stop a run from being skipped in silence.
#   StartWhenAvailable       the PC was off or asleep at the trigger time
#   WakeToRun                asleep rather than off (ignored when the power
#                            plan disallows wake timers)
#   *OnBatteries             a laptop unplugged at the time
#   RestartCount             the machine was too busy to start
#   IgnoreNew                runs sit closer together now; never overlap
#   ExecutionTimeLimit 2h    a killed run records a failure the monitor
#                            reports, so leave room rather than cut it short
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $Triggers `
    -Principal $Principal `
    -Settings $settings `
    -Description "PACE LAB auto-ingest: mykeibadb.exe -> batch.py (Tue/Fri/Sat/Sun)" `
    -Force | Out-Null

Write-Host "Registered: $TaskName"
Write-Host "  Tue 21:00 / Fri 10:00 / Fri 21:00 / Sat 10:00 / Sat 21:00 / Sun 21:00"
Write-Host ""
Write-Host "Check: Get-ScheduledTask -TaskName '$TaskName' | Select-Object TaskName, State"
Write-Host "Next runs: Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host "Manual test run: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Note: this task only runs while $env:USERNAME is logged on."
Write-Host "A reboot without auto-logon stops it silently; the daily freshness"
Write-Host "check on GitHub Actions is what catches that."
