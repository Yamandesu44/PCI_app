@echo off
:: 出走表取り込み — Windows タスクスケジューラから毎朝 3:00 に実行する。
:: タスク名: PCI_Ingest_Entries
:: トリガー: 毎日 03:00 JST
::
:: 手動実行: scripts\daily_entries.bat
:: セットアップ: scripts\setup_task_scheduler.ps1 を管理者権限で実行する。

cd /d "%~dp0\.."
powershell -ExecutionPolicy Bypass -File scripts\run_batch.ps1 -Step entries
