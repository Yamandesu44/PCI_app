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
      Thu 17:00  Entry list without numbers, published Thursday 16:00.
      Fri 11:00  Saturday's draw, published Friday just after 10:00.
      Fri 13:00  Backup for the 11:00 run.
      Sat 11:00  Sunday's draw, published Saturday just after 10:00.
      Sat 13:00  Backup for the 11:00 run.
      Sat 21:00  Saturday results.
      Sun 21:00  Sunday results.

    Why these times:
      Taken from JRA's own publication schedule, not guessed:
      https://jra.jp/faq/pop02/2_2.html

        Thu 16:00+  entry list, no horse or bracket numbers
        Day-before 10:00+  entry list WITH numbers
          -> Saturday's races land Friday, SUNDAY'S LAND SATURDAY.

      That last point is easy to get wrong. Sunday's field is not
      available on Friday, so a Friday-only schedule leaves the whole
      Sunday card missing until Saturday whatever else is done.

      JRA also notes its own site needs "about 15 minutes" after each
      publication before the data is visible, so treat 10:00 as a
      floor and not a start. Running at 10:00 sharp was tried and
      returned only the special entries; the same day at 12:03
      returned all 36 races. Hence 11:00, with 13:00 behind it.

      Each run re-reads a rolling window (10 days back through the
      future), so a missed run is picked up by the next one. The
      schedule controls how quickly data appears, not whether it
      arrives at all -- extra runs are cheap insurance.

      Saturday 21:00 covers the results. Without it, Saturday's
      results only land on Sunday evening, leaving the board showing
      zero confirmed races across Saturday night and Sunday morning,
      when people are reviewing Saturday and handicapping Sunday.

      21:00 is a margin over the last race (confirmed around 16:30),
      not a measured figure.

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

# Check for elevation up front. Without it the script does everything and then
# fails on the final call with "Access denied" wrapped in a CIM error, which
# does not say the words "run as administrator".
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw @"
Administrator rights are required to register a scheduled task.

Open PowerShell as Administrator (Start > type "PowerShell" > right-click >
"Run as administrator"), then:

  cd "$(Split-Path $PSScriptRoot -Parent)"
  powershell -ExecutionPolicy Bypass -File .\scripts\setup_task_scheduler.ps1
"@
}

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
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At "17:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday   -At "11:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday   -At "13:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At "11:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At "13:00"
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
    -Description "PACE LAB auto-ingest: mykeibadb.exe -> batch.py (Tue/Thu/Fri/Sat/Sun)" `
    -Force | Out-Null

Write-Host "Registered: $TaskName"
Write-Host "  Tue 21:00 / Thu 17:00"
Write-Host "  Fri 11:00, 13:00  (Saturday's draw)"
Write-Host "  Sat 11:00, 13:00  (Sunday's draw) / Sat 21:00 (results)"
Write-Host "  Sun 21:00 (results)"
Write-Host ""
Write-Host "Check: Get-ScheduledTask -TaskName '$TaskName' | Select-Object TaskName, State"
Write-Host "Next runs: Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host "Manual test run: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Note: this task only runs while $env:USERNAME is logged on."
Write-Host "A reboot without auto-logon stops it silently; the daily freshness"
Write-Host "check on GitHub Actions is what catches that."
