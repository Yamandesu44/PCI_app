@echo off
REM 日本語ログをコマンドプロンプトとPythonでUTF-8へ統一する。
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
REM mykeibadb sync - run from Windows Task Scheduler Fri/Sat 10:00, Sun 18:00.
REM Task name: PCI_Sync_Mykeibadb
REM
REM What it does: mykeibadb.exe (JV-Link -> MySQL) then batch.py (MySQL -> PostgreSQL,
REM entries + results + special-entries).
REM Manual run: scripts\sync_mykeibadb.bat
REM Setup: run scripts\setup_task_scheduler.ps1 as Administrator.
REM Requires: MYKEIBADB_EXE_PATH (full path to mykeibadb.exe) set in .env.

cd /d "%~dp0\.."
powershell -ExecutionPolicy Bypass -File scripts\run_mykeibadb_full_sync.ps1
