# JV-Link サンプルフィクスチャ

JV-Link（Windows専用 COM）を使わずに domain / application / API / ingestion-worker の
開発・検証を進めるためのサンプルデータを格納するディレクトリ（ADR-0002）。

## 利用方針

- 構造化 JSON（`sample_race_entries.json` / `sample_race_result.json`）を単一ソースとする
- `FixtureJvLinkClient` が JSON を読み、**byte 正確**な JV-Data 固定長レコードへ変換する
  （`fixture_client.py` の `_json_*` 生成関数。jv_spec のオフセットに一致）
- **生データ・認証情報は一切コミットしない**（法務: C2、セキュリティ: CLAUDE.md）

## なぜ JSON 生成か（旧 .txt 方式からの変更）

JV-Data のオフセットは **byte** 単位で、馬名など全角フィールドを跨ぐと char 位置と
ズレる。手書き `.txt` の固定長レコードは末尾空白の欠落や全角ズレで byte 単位パーサと
不整合になりやすい。JSON から bytearray を組み立てて生成することで、
本番（JV-Link）と同一のパーサパスを byte 正確に再現できる。

## サンプルデータの編集

- レース・出走馬: `sample_race_entries.json`（race_info + entries[]）
- 確定成績: `sample_race_result.json`（results[]）

固有名詞は架空のもの（サンプルホース等）を使用し、実データは置かない。

## 動作確認

```bash
# fixtures → パーサ → モデル生成の全パスを検証
cd apps/ingestion-worker && pytest tests/test_batch_e2e.py tests/test_fixture_client.py

# 実際にバッチを流す（API 未起動時は送信のみ失敗、パースは成功）
PYTHONPATH=src python -m ingestion.batch --mode fixture
```
