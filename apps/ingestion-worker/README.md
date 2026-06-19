# PCI ingestion-worker

JRA-VAN DataLab（JV-Link）から競馬データを取得し、Ingest API に投入する日次バッチ。

ADR-0002: Windows 専用 COM コンポーネント（JV-Link）を使うため、
          ワーカーは Windows PC / VM 上で動作する。
          開発・テストは `fixtures/` の JSON を使うため Windows 不要。

## 構成

```
src/ingestion/
├── models.py               # 中間データモデル（HorseRecord, EntryRecord, ...）
├── parser/
│   ├── common.py           # 共通ユーティリティ（バイト抽出・コード変換）
│   ├── ra_parser.py        # RA レコード（レース詳細）パーサ
│   ├── se_parser.py        # SE レコード（馬毎レース情報）パーサ
│   └── master_parsers.py   # UM / KS / CH マスタパーサ
├── client/
│   ├── base.py             # JvLinkClient Protocol
│   ├── fixture_client.py   # 開発用 JSON クライアント
│   └── windows_client.py   # 本番 Windows COM クライアント
├── ingest_api.py           # Ingest API HTTP クライアント
└── batch.py                # バッチランナー（エントリーポイント）
```

## セットアップ

```bash
# 開発環境（Linux / macOS）
pip install -e ".[dev]"

# 本番環境（Windows）
pip install -e ".[win]"

# 環境変数
cp .env.example .env
# .env を編集して API_BASE_URL / INGEST_TOKEN を設定
```

## 実行

```bash
# 開発モード（fixtures/ の JSON を使う）
python -m ingestion.batch --mode fixture

# 本番モード（Windows + JV-Link COM）
python -m ingestion.batch --mode jvlink --date 20260619

# ステップ単位で実行
python -m ingestion.batch --mode fixture --step masters   # マスタのみ
python -m ingestion.batch --mode fixture --step entries   # 出走表のみ
python -m ingestion.batch --mode fixture --step results   # 確定成績のみ
```

## テスト

```bash
cd apps/ingestion-worker
pytest tests/
```

## Ingest API エンドポイント

| エンドポイント | メソッド | 説明 |
|---|---|---|
| `/internal/ingest/horses` | POST | 馬マスタ一括 Upsert |
| `/internal/ingest/jockeys` | POST | 騎手マスタ一括 Upsert |
| `/internal/ingest/trainers` | POST | 調教師マスタ一括 Upsert |
| `/internal/ingest/entries` | POST | 出走表登録 |
| `/internal/ingest/results` | POST | 確定成績登録 |

全エンドポイントは `X-Ingest-Token` ヘッダーで認証（`INGEST_TOKEN` 未設定時はスキップ）。

## JV-Link レコード種別

| 種別 | 内容 | パーサ |
|---|---|---|
| RA | レース詳細 | `ra_parser.py` |
| SE | 馬毎レース情報（出走前/確定後） | `se_parser.py` |
| UM | 競走馬マスタ | `master_parsers.py` |
| KS | 騎手マスタ | `master_parsers.py` |
| CH | 調教師マスタ | `master_parsers.py` |

## 注意事項

- JV-Link 認証情報（SID）は `.env` で管理し、**絶対にコミットしない**
- 生データ（JV-Data レコード）の再配布は JRA-VAN 規約上禁止
- `windows_client.py` は Windows 専用。Linux では `FixtureJvLinkClient` を使用
- SE レコードのバイト位置は JV-Data仕様書 Ver.3.0 準拠（実際の JV-Link 出力との照合推奨）
