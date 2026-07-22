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

# mykeibadb MySQL 読み取りを使う場合
python -m pip install -e ".[mysql]"

# Windows で JV-Link と mykeibadb の両方を使う場合
python -m pip install -e ".[win,mysql]"

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
python -m pip install -e ".[win,mysql]"
```

`.env` には JRA-VAN DataLab の利用キーを設定します。

```env
API_BASE_URL=http://localhost:8000
INGEST_TOKEN=
JV_LINK_SID=ここに利用キーを設定

# mykeibadb を使う場合
MYKEIBADB_HOST=localhost
MYKEIBADB_PORT=3306
MYKEIBADB_USER=root
MYKEIBADB_PASSWORD=
MYKEIBADB_DATABASE=mykeibadb
MYKEIBADB_EXCLUDE_RACE_KEYS=
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

# 過去成績を長期で反映したい時（例: 2000年以降）
# まず TARGET / mykeibadb 側で JRA-VAN から MySQL へ取り込みます。
# PCI_app 側の mykeibadb 読み取りは、現時点では週末の特別登録のみ対応しています。
# 確定済み過去成績を MySQL から反映するには、mykeibadb の通常レース・成績テーブル対応が必要です。

# 週末の特別登録・出馬表など未来データの取得可否を確認する時
python -m ingestion.probe_race_options --date 20260624 --date-to 20260628 --days-back 14

# probe でデータが返った option を使い、未来日の予想対象を取り込む（例: option=4）
python -m ingestion.batch --mode jvlink --date 20260617 --date-to 20260628 --race-option 4 --step entries

# mykeibadb の特別登録テーブルから週末の予想対象を取り込む
python -m ingestion.batch --mode mykeibadb --date 20260627 --date-to 20260628 --step special-entries

# ステップ単位で実行
python -m ingestion.batch --mode fixture --step masters   # マスタのみ
python -m ingestion.batch --mode fixture --step entries   # 出走表のみ
python -m ingestion.batch --mode fixture --step results   # 確定成績のみ
python -m ingestion.batch --mode fixture --step forecasts # 今日以降の予想martを事前生成
```

`--mode jvlink` では、同一プロセス内で取得した RACE / DIFF レコードを再利用します。
JV-Link は同じデータを短時間に複数回 `JVOpen` すると2回目以降が空になる場合があるため、
通常は `--step all` のまま一度で取り込んでください。

先週までの確定成績は通常データなので `--race-option 1`（デフォルト）を使います。
週末の特別登録・出馬表など、未来日の予想対象は先に
`python -m ingestion.probe_race_options --date 20260624 --date-to 20260628 --days-back 14`
で `option=1..4` の取得可否を確認し、`target_dates=[20260627:..., 20260628:...]`
が出る `fromtime` と option を、`--date` と `--race-option` に指定してください。

`JVOpen 失敗: エラーコード -1（該当データなし）` は、JV-Link 自体の起動失敗ではなく、
指定した `fromtime` / `option` の組み合わせで返るデータがない状態です。
特別登録のような未来データでは、レース当日 `20260627` を `--date` にするより、
データが公開・更新された日（例: `20260624`）から問い合わせる方が取得できる場合があります。

mykeibadb を使う場合は、JRA-VAN から mykeibadb 側 MySQL へ取り込み済みであることが前提です。
現在の `--mode mykeibadb` は `TOKUBETSU_TOROKUBA` / `TOKUBETSU_TOROKUBAGOTO_JOHO`
を読み、週末の特別登録を PCI_app の `races` / `race_entries` に変換して Ingest API へ投入します。
2000年以降の確定済み過去成績を MySQL から反映する場合は、mykeibadb の通常レース・成績テーブルを
読み取る取り込み処理を追加してください。
mykeibadb 側に実施されない特別登録が残っている場合は、`MYKEIBADB_EXCLUDE_RACE_KEYS` に
カンマ区切りで race_key を指定すると取り込み対象から除外できます。

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
- SE レコードのバイト位置は JV-Data仕様書 Ver.3.0 準拠（実際の JV-Link 出力との照合推奨。
  Ver.3.0のまま変わっていないのか、UM/KS/CH同様Ver.4.9相当で校正済みなのかは未確認 → `docs/SPEC.md §9-8`）
- JV-Linkの新バージョン追従・バイトオフセットの再検証手順は `JV_SPEC_MAINTENANCE_GUIDE.md` 参照
