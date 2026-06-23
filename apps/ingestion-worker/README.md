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
python -m pip install -e ".[win]"

# 環境変数
cp .env.example .env
# .env を編集して API_BASE_URL / INGEST_TOKEN / JV_LINK_SID を設定
```

Windows のコマンドプロンプトで作業する場合:

```bat
cd /d C:\Users\yuuta\PCI_app\apps\ingestion-worker
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -e ".[win]"
copy .env.example .env
notepad .env
```

既に Claude Code で使っていた `.venv` がある場合は、新規作成せずに有効化だけで構いません。

```bat
cd /d C:\Users\yuuta\PCI_app\apps\ingestion-worker
.venv\Scripts\activate.bat
python -m pip install -e ".[win]"
```

`.env` には JRA-VAN DataLab の利用キーを設定します。

```env
API_BASE_URL=http://localhost:8000
INGEST_TOKEN=
JV_LINK_SID=ここに利用キーを設定
```

`No module named 'ingestion'` が出る場合は、`python -m pip install -e ".[win]"`
が未実行です。もう一度 `apps\ingestion-worker` で上記コマンドを実行してください。

`クラスが登録されていません` が出る場合は、JV-Link COM が現在の Python から見えていません。
以前使っていた `.venv` を有効化して実行してください。それでも解消しない場合は、
JV-Link のインストール状態と Python の 32/64bit が JV-Link COM と合っているかを確認してください。

## 実行

```bash
# 開発モード（fixtures/ の JSON を使う）
python -m ingestion.batch --mode fixture

# 本番モード（Windows + JV-Link COM）
python -m ingestion.batch --mode jvlink --date 20260619

# 期間指定（先週結果 + 今週特別登録などをまとめて取得する時）
python -m ingestion.batch --mode jvlink --date 20260613 --date-to 20260628

# ステップ単位で実行
python -m ingestion.batch --mode fixture --step masters   # マスタのみ
python -m ingestion.batch --mode fixture --step entries   # 出走表のみ
python -m ingestion.batch --mode fixture --step results   # 確定成績のみ
```

`--mode jvlink` では、同一プロセス内で取得した RACE / DIFF レコードを再利用します。
JV-Link は同じデータを短時間に複数回 `JVOpen` すると2回目以降が空になる場合があるため、
通常は `--step all` のまま一度で取り込んでください。

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
