@echo off
:: mykeibadb 同期 — Windows タスクスケジューラから1日4回（9/13/18/21時）実行する。
:: タスク名: PCI_Sync_Mykeibadb
::
:: 実行内容: mykeibadb.exe（JV-Link→MySQL） → batch.py（MySQL→PostgreSQL 出走表・成績）
:: 手動実行: scripts\sync_mykeibadb.bat
:: セットアップ: scripts\setup_task_scheduler.ps1 を管理者権限で実行する。
:: 前提: .env に MYKEIBADB_EXE_PATH（mykeibadb.exe のフルパス）を設定しておくこと。

cd /d "%~dp0\.."
powershell -ExecutionPolicy Bypass -File scripts\run_mykeibadb_full_sync.ps1
