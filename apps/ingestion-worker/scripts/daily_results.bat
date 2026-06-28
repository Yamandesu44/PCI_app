@echo off
:: 確定成績取り込み — Windows タスクスケジューラから毎日 17:30 に実行する。
:: タスク名: PCI_Ingest_Results
:: トリガー: 毎日 17:30 JST（最終レース＝阪神・中山の最終が概ね 17:00 前後）
::
:: 手動実行: scripts\daily_results.bat
:: セットアップ: scripts\setup_task_scheduler.ps1 を管理者権限で実行する。

cd /d "%~dp0\.."
powershell -ExecutionPolicy Bypass -File scripts\run_batch.ps1 -Step results
