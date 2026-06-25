# Claude Code 引き継ぎメモ（2026-06-25）

## 前提

- リポジトリ: `Yamandesu44/PCI_app`
- 作業ブランチ: `claude/sweet-einstein-ilnaov`
- アプリの方向性: 「PCI分析ツール」から「展開予想ツール」へ転換する
- UI方針: Vercel Dashboard / Linear / Notion / Stripe Dashboard に近い、Minimal / Data First / Modern Racing Analytics
- ユーザー向け説明方針:
  - UI上では PCI / RPCI の実数値を前面に出しすぎない
  - 初心者向けコメントでは実数値と専門用語を極力抑える
  - コードコメントは日本語

## 現在の状態

最新の主なコミットは以下。

```text
9f1334e fix(ingestion): map wmykeibadb race columns
ee4452f fix(ingestion): use server side mysql cursor
b1f6be9 fix(ingestion): stream mykeibadb imports
8fbebf6 fix(ingestion): support mykeibadb table names
4a18ae3 feat(ingestion): import full mykeibadb data
6ca6e59 fix(races): sanitize confirmed race names
796c057 fix(web): avoid stale forecast lookups
7df1a91 fix(races): improve list filtering and names
14ff5a2 docs(ingestion): clarify MySQL historical data import
8baa019 feat(ingestion): chunk long date range imports
9f5affe feat(forecast): add horse pace affinity scoring
ec1299d fix(data): prune excluded races during ingestion
```

## 実装済みの大きな変更

### レース一覧 UI

- 開催日ごとに表示レースを選べる構成へ変更。
- netkeiba を参考に、開催日、競馬場、R番号、レース名、距離、出走前/確定後の状態が見やすいカード型へ寄せた。
- 「今週末の予想対象」「その他の出走前レース」「確定後レース」を分離。
- 確定済みレースに出走前レース扱いが混ざらないようフィルタリングを改善。
- 架空の阪神11Rを除外する仕組みを追加。

### レース詳細 / 展開予想 UI

- Hero Section を追加。
- 情報優先順位を以下へ変更。
  1. 想定展開
  2. 展開恩恵馬 TOP5
  3. 展開信頼度
  4. ペース分析
  5. PCI詳細データ
- PCI詳細は Accordion に格納し、初心者には最初から見せすぎない形に変更。
- 「評価を下げたい馬」セクションを追加。
- 「この展開をやさしく解説」は、実数値や専門用語を抑えたコメントへ変更。

### 予想ロジック

- 各馬の過去成績から「得意なレース質」を見る方向へ拡張。
- 展開と馬の相性を評価する `horse pace affinity` 系のスコアリングを追加。
- PCI / RPCI は内部ロジックでは使うが、UIでは「速い流れ」「落ち着いた流れ」などに翻訳して見せる方針。

### mykeibadb / MySQL 取り込み

- `ingestion-worker` に `--mode mykeibadb` を追加。
- mykeibadb の MySQL から以下を読み取り、PCI_app の FastAPI Ingest API へ投入する。
  - マスタ
  - 出走表
  - 確定後成績
  - 特別登録
- 長期間取り込み用に `--chunk-days` を追加。
- 大量データで `MemoryError` が出ないよう、PyMySQL の server-side cursor を使うよう変更。
- wmykeibadb が作成する `race_shosai` の大文字英字列名に対応。
  - `KAISAI_NEN`
  - `KAISAI_GAPPI`
  - `KEIBAJO_CODE`
  - `KAISAI_KAI`
  - `KAISAI_NICHIME`
  - `RACE_BANGO`
  - `KYOSOMEI_HONDAI`
  - `KYOSO_JOKEN_MEISHO`
  - `KYORI`
  - `TRACK_CODE`
  - `ZENHAN_3F`
  - `KOHAN_3F`

## 重要ファイル

### Web

- `apps/web/src/app/page.tsx`
  - レース一覧画面。
- `apps/web/src/components/RaceForecastDashboard.tsx`
  - 展開予想画面の中心。
- `apps/web/src/components/RaceHero.tsx`
  - レース詳細 Hero Section。
- `apps/web/src/components/PaceHeadline.tsx`
  - PCI / RPCI をユーザー向け表現へ変換する見出し。
- `apps/web/src/lib/races.ts`
  - レース一覧の表示分類・整形。
- `apps/web/src/lib/pace.ts`
  - ペース表現・初心者向けコメントの変換。

### API

- `apps/api/src/pci/application/forecast_use_cases.py`
  - 展開予想のユースケース。
- `apps/api/src/pci/domain/services.py`
  - PCI / RPCI / 展開評価系のドメインロジック。
- `apps/api/src/pci/infrastructure/repositories.py`
  - DB読み取り・レース名などの返却元。
- `apps/api/src/pci/presentation/app.py`
  - FastAPI エンドポイント。

### ingestion-worker

- `apps/ingestion-worker/src/ingestion/batch.py`
  - 取り込みコマンド本体。
- `apps/ingestion-worker/src/ingestion/client/mykeibadb_client.py`
  - mykeibadb MySQL 読み取り。
- `apps/ingestion-worker/src/ingestion/ingest_api.py`
  - FastAPI Ingest API クライアント。
- `apps/ingestion-worker/tests/test_mykeibadb_client.py`
  - mykeibadb 変換テスト。

## ローカル起動手順

### 1. DB

```bat
cd /d C:\Users\yuuta\PCI_app
docker-compose up -d db
```

### 2. FastAPI

Windows で `uvicorn --reload` が `ValueError: too many file descriptors in select()` を出す場合がある。  
その場合は `--reload` を外すか、監視対象を `src` に絞る。

```bat
cd /d C:\Users\yuuta\PCI_app\apps\api
.venv\Scripts\activate.bat
alembic upgrade head
uvicorn pci.presentation.app:app --host 127.0.0.1 --port 8000 --reload --reload-dir src
```

それでも不安定なら以下。

```bat
uvicorn pci.presentation.app:app --host 127.0.0.1 --port 8000
```

確認URL:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

### 3. Next.js

```bat
cd /d C:\Users\yuuta\PCI_app\apps\web
npm run dev
```

確認URL:

```text
http://localhost:3000
```

## mykeibadb の .env

`apps/ingestion-worker\.env` に以下を入れる。

```env
API_BASE_URL=http://localhost:8000
INGEST_TOKEN=
JV_LINK_SID=

MYKEIBADB_HOST=localhost
MYKEIBADB_PORT=3306
MYKEIBADB_USER=root
MYKEIBADB_PASSWORD=ここにMySQLのパスワード
MYKEIBADB_DATABASE=mykeibadb
MYKEIBADB_EXCLUDE_RACE_KEYS=
```

## mykeibadb からアプリへ取り込む手順

前提として、wmykeibadb.exe 側で JRA-VAN から MySQL へデータ投入済みであること。

必要データ:

- `RA` / `race_shosai`
  - レース詳細、距離、馬場、レース名、ラップなど。
- `SE` / `umagoto_race_joho`
  - 馬ごとのレース成績、通過順、上がりなど。
- `UM` / `kyosoba_master2`
  - 競走馬マスタ。
- `KS` / `kishu_master`
  - 騎手マスタ。
- `CH` / `chokyoshi_master`
  - 調教師マスタ。
- `TOKUBETSU_TOROKUBA`
  - 特別登録レース。
- `TOKUBETSU_TOROKUBAGOTO_JOHO`
  - 特別登録馬。

1年分を投入する例:

```bat
cd /d C:\Users\yuuta\PCI_app\apps\ingestion-worker
.venv\Scripts\activate.bat
python -m pip install -e ".[win,mysql]"
python -m ingestion.batch --mode mykeibadb --date 20250625 --date-to 20260625 --step all --chunk-days 7
```

今週末の出馬表・特別登録だけを入れる例:

```bat
python -m ingestion.batch --mode mykeibadb --date 20260627 --date-to 20260628 --step special-entries
```

## 最近対応したエラー

### `MemoryError`

大量テーブルを `fetchall()` していたことが原因。  
server-side cursor と `fetchmany()` へ変更済み。

### `mykeibadb のテーブルが見つかりません: UM`

実際の mykeibadb テーブル名が `kyosoba_master2` などだったため、候補テーブル名を追加済み。

### `競馬場コードを特定できません`

`race_shosai` の列が `KEIBAJO_CODE` だったため、wmykeibadb の大文字英字列名を追加済み。  
数値型の `5` も `05` へ変換するよう修正済み。

## まだ注意が必要な点

- mykeibadb 側のテーブル名・列名は環境やバージョンで揺れる可能性がある。
- 次に列名エラーが出た場合は、エラー全文に出ている列一覧を `mykeibadb_client.py` の候補列へ追加する。
- 確定後レース名が `@` になる場合は、API側のレース名補正か、mykeibadb 側の `KYOSOMEI_HONDAI` / `KYOSOMEI_RYAKUSHO_10` の取得状態を確認する。
- 1年分取り込みは時間がかかる。途中で落ちたら、落ちたチャンクの日付から再実行する。
- API起動時の `--reload` は Windows 環境で不安定になりやすい。大量ファイルがある環境では `--reload-dir src` を付ける。

## 次に推奨する作業

1. 1年分の取り込みを完走させ、APIの `/api/v1/races` と Web一覧で表示を確認する。
2. 確定後レース名が全て正しく表示されるか確認する。
3. 今週末の出馬表確定データで、展開恩恵馬 TOP5 と評価を下げたい馬が実データ由来になっているか確認する。
4. 馬ごとの得意レース質ロジックを、過去成績の件数・距離・馬場・脚質ごとに検証する。
5. UI上の初心者向け説明が、PCI/RPCI の実数値を出しすぎていないか最終確認する。

## Claude Code への依頼時のおすすめ文面

```text
このリポジトリは PCI_app です。docs/handoff-claude-code-2026-06-25.md を読んでから作業してください。
現在は mykeibadb MySQL から1年分の実データを ingestion-worker 経由で FastAPI/PostgreSQL に投入し、
Next.js のレース一覧・展開予想画面で確認する段階です。

まず git pull origin claude/sweet-einstein-ilnaov を行い、最新コミット 9f1334e 以降の状態で進めてください。
ユーザー向け出力は日本語、コードコメントも日本語でお願いします。
```
