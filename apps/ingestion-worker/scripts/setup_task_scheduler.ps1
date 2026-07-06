<#
.SYNOPSIS
    Register the mykeibadb sync task in Windows Task Scheduler.

.DESCRIPTION
    Run this as Administrator.
    Re-running overwrites any existing task with the same name.

    Registers:
      PCI_Sync_Mykeibadb  daily at 09:00 / 13:00 / 18:00 / 21:00 JST
        Runs mykeibadb.exe (JV-Link -> local MySQL) then batch.py
        (MySQL -> PostgreSQL entries + results) end to end, via
        scripts\sync_mykeibadb.bat.

    Prerequisites:
      MYKEIBADB_EXE_PATH (full path to mykeibadb.exe) is set in .env.
      "Pause on exit" is unchecked in wmykeibadb.exe (otherwise an
      unattended run will hang waiting for a keypress).

.EXAMPLE
    # Open PowerShell as Administrator and run:
    .\scripts\setup_task_scheduler.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$WorkerDir = Split-Path $PSScriptRoot -Parent
$SyncBat = Join-Path $WorkerDir "scripts\sync_mykeibadb.bat"

if (-not (Test-Path $SyncBat)) {
    throw "Batch file not found: $SyncBat"
}

# Run the task as the current logged-in user (no password needed, but only
# runs while that user is logged on). For a headless server, switch to
# -RunLevel Highest -User "SYSTEM" instead.
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

$Times = @("09:00", "13:00", "18:00", "21:00")
$Triggers = $Times | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$SyncBat`""
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 0 `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName "PCI_Sync_Mykeibadb" `
    -Action $action `
    -Trigger $Triggers `
    -Principal $Principal `
    -Settings $settings `
    -Description "PCI App auto-ingest: mykeibadb.exe -> batch.py (4x daily)" `
    -Force | Out-Null

Write-Host "Registered: PCI_Sync_Mykeibadb (daily at $($Times -join ' / '))"
Write-Host ""
Write-Host "Check: Get-ScheduledTask -TaskName 'PCI_Sync_Mykeibadb' | Select-Object TaskName, State"
Write-Host "Manual test run: Start-ScheduledTask -TaskName 'PCI_Sync_Mykeibadb'"
