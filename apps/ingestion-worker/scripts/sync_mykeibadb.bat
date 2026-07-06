@echo off
REM mykeibadb sync - run from Windows Task Scheduler 4x/day (9/13/18/21h).
REM Task name: PCI_Sync_Mykeibadb
REM
REM What it does: mykeibadb.exe (JV-Link -> MySQL) then batch.py (MySQL -> PostgreSQL,
REM entries + results).
REM Manual run: scripts\sync_mykeibadb.bat
REM Setup: run scripts\setup_task_scheduler.ps1 as Administrator.
REM Requires: MYKEIBADB_EXE_PATH (full path to mykeibadb.exe) set in .env.

cd /d "%~dp0\.."
powershell -ExecutionPolicy Bypass -File scripts\run_mykeibadb_full_sync.ps1
