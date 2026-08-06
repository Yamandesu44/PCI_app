# PCI App — 競馬展開予想 SaaS

JRA-VAN DataLab の JV-Link から取得した競馬データを元に、レース展開（ペース・脚質適性）を
自動分析する SaaS アプリ。

> **コアバリュー:** 「PCI を理解していない競馬ファンでも展開予想を活用できること」
>
> TARGET の完全再現ではなく、上級者の暗黙知（展開判断・展開合致馬抽出）を
> **説明可能なアルゴリズム**に変換することが目的。

---

## 現在のステータス

**個人利用MVPは稼働中。少人数ロケテストへ向けて予想検証データを蓄積中。**

| 領域 | 状態 |
|---|---|
| ドメイン核（PCI / 脚質 / 想定RPCI / PAI / 展開シナリオ） | ✅ 実装済み・テスト済み |
| アプリケーション層（ユースケース） | ✅ 実装済み |
| DB（core / mart）+ Alembic + Repository | ✅ 実装済み（mart 永続化込み） |
| FastAPI（`/forecast`・レース詳細） | ✅ 実装済み |
| 型共有（`packages/api-client`） | ✅ OpenAPI → TypeScript 生成 |
| フロントエンド（`apps/web` / Next.js） | ✅ レース一覧・展開予想・確定後分析・予想検証 |
| ingestion-worker（mykeibadb / JV-Link） | ✅ Windows自動同期・鮮度/完全性監視・失敗通知 |
| 実データ | ✅ mykeibadb（MySQL）からPostgreSQLへ同期 |
| 予想精度の期間外検証 | ⏳ 2026-07-25以降の事前予想を蓄積中 |
| 少人数ロケテスト | ✅ Quick Tunnel実URLで認証・API疎通・代表3レースを確認済み。招待開始時だけ公開する |

ローカル起動: API は [`apps/api/README.md`](./apps/api/README.md)、Web は [`apps/web/README.md`](./apps/web/README.md) を参照。

---

## ドキュメント

| 種別 | 場所 |
|---|---|
| プロジェクト指針（必読） | [`CLAUDE.md`](./CLAUDE.md) |
| 現在の引き継ぎ | [`docs/HANDOFF.md`](./docs/HANDOFF.md) |
| 現行仕様 | [`docs/SPEC.md`](./docs/SPEC.md) |
| ロケテスト手順 | [`docs/LOCATION_TEST.md`](./docs/LOCATION_TEST.md) |
| ユビキタス言語 | [`docs/domain/ubiquitous-language.md`](./docs/domain/ubiquitous-language.md) |
| 設計書 | [`docs/design/`](./docs/design/) |
| ADR（意思決定記録） | [`docs/adr/`](./docs/adr/) |

### 設計書（docs/design/）
1. [要求整理](./docs/design/01-requirements.md)
2. [DDDドメインモデル](./docs/design/02-domain-model.md)
3. [データモデル設計](./docs/design/03-data-model.md)
4. [API設計](./docs/design/04-api-design.md)
5. [開発ロードマップ](./docs/design/05-roadmap.md)
6. [テスト戦略](./docs/design/06-test-strategy.md)
7. [技術的リスクと残課題](./docs/design/07-risks-and-open-questions.md)
8. [デプロイ構成](./docs/design/08-deployment.md)

### ADR（docs/adr/）
- 0001: アーキテクチャスタイル（モジュラーモノリス + レイヤードDDD）
- 0002: JV-Link 取り込み方式（Windowsワーカー分離）
- 0003: モノレポ構成
- 0004: PCI / RPCI / PCI3 計算式の隔離方針
- 0005: 想定RPCI 予測戦略（MVPルールベース + ML疎結合IF）
- 0006: DB 3層化（raw / core / mart）
- 0007: フロントエンド構成（Next.js App Router + OpenAPI 型共有）
- 0008: 展開コメント生成方式（ルールベースNLG + LLM疎結合IF）

---

## アーキテクチャ概要

```
[Windows ingestion-worker]
    ↓ (JV-Link/COM → PostgreSQL or Ingest API)
[PostgreSQL (raw / core / mart)]
    ↓
[FastAPI (apps/api)] ──REST──► [Next.js (apps/web)] → Vercel
```

詳細は [`CLAUDE.md`](./CLAUDE.md) および [`docs/`](./docs/) を参照。

---

## 現行スコープ

- 対象: **JRA 中央競馬のみ**、過去5年分
- 更新: **日次バッチ**（前日夜〜当日朝）、リアルタイム速報は対象外
- 公開範囲: 現在は**個人利用・検証用途**。次段階は招待した少人数だけのロケテスト
- データ表示: 生データやPCI/RPCI等の内部実数値を前面に出さず、独自の言葉・段階評価へ翻訳
- 認証・課金: 少人数テスト用の共有認証のみ実装。個別アカウント・権限・課金は対象外

詳細: [`docs/design/01-requirements.md`](./docs/design/01-requirements.md)

## デプロイ

### API（Cloud Run）

デプロイ先は Cloud Run を選定した（東京リージョンがあり、SSR の経路
「Vercel のリージョン ↔ API のリージョン」を短くできるため。判断の経緯は
`docs/HANDOFF.md`）。`apps/api/Dockerfile` は PaaS 固有の仕組みを使っていないので、
別の環境へ移す場合もそのまま使える。ポートは `PORT` 環境変数で受ける。

デプロイは `.github/workflows/deploy-cloudrun.yml` を**手動実行**する。
push で自動デプロイしないのは、作業ブランチへの push で本番が更新される事故を
避けるため。必要な GCP 側の準備とリポジトリ変数はワークフロー冒頭に列挙してある。

**Cloud Run 固有の注意:**

- `RATE_LIMIT_TRUSTED_PROXIES=1` を設定する。前段にロードバランサが入るため、
  未設定だと全利用者が同じキーへ集約され、レート制限が実質「全体で N 回/分」になる。
- ゼロスケールするため起動が繰り返される。モデル読み込みは起動時に済ませているので
  （`warm_up`）、最初の利用者が待たされることはない。
- `--max-instances` を必ず設定する。上限が無いと異常時に従量課金が青天井になる。

#### デプロイ直後の確認

```bash
cd apps/api
python -m scripts.check_deployment --base-url https://<サービスのURL> --token "$PUBLIC_API_TOKEN"
```

設定漏れは**落ちる形では現れない**。一見正常に応答したまま、次の状態になる。

| 状態 | 起きること |
|---|---|
| `PUBLIC_API_TOKEN` 未設定 | 到達できる相手は誰でも全データを読める（生データ再配布の禁止に抵触する） |
| `MODELS_DIR` の解決失敗 | 例外を出さずルールベースへ落ち、精度だけ静かに下がる |
| `CORS_ALLOW_ORIGINS` が緩い | 任意のサイトからブラウザ経由で読み出せる |

いずれも外から検出できるので、デプロイのたびに走らせる。読み取りのみで、
問題があれば終了コード1で落ちる。外から判定できない項目（`RATE_LIMIT_TRUSTED_PROXIES`
など）は「確認できない項目」として最後に並ぶ。

### PostgreSQL（Supabase・東京）

Cloud SQL に無料枠が無いため、東京リージョンのマネージド Postgres を併用する。
Supabase を選定（無料枠 DB 500MB・東京リージョン）。実測 123MB に対して4倍の余裕があり、
コアの増加は年 26MB 程度。mart 層は世代を掃除すれば頭打ちにできる（下記）。

Aiven を検討したが、**無料プランはリージョンを選べず**（DigitalOcean 固定・東京なし）、
東京を使うには有料プランが要るため見送った。判断の経緯は `docs/HANDOFF.md`。

#### 接続文字列（ここを間違えると繋がらない／断続的に落ちる）

**必ずプーラー（Supavisor）経由の、ポート 5432 の文字列を使う。**

| 種類 | ホスト・ポート | 使えるか |
|---|---|---|
| 直結 | `db.<ref>.supabase.co:5432` | **不可**。IPv6 のみで、Cloud Run の外向きは IPv4 |
| プーラー session | `...pooler.supabase.com:**5432**` | **これを使う** |
| プーラー transaction | `...pooler.supabase.com:**6543**` | **不可**。下記 |

transaction モードは文ごとに接続を割り当て直すため prepared statement が失われる。
pg8000 は内部でこれを使うので、**繋がった後に断続的に失敗する**——起動直後は動くのに
時々落ちる、という最も追いにくい壊れ方になる。

接続文字列はダッシュボードからコピーしたものをそのまま `DATABASE_URL` へ貼ってよい。
ドライバ部分だけ `postgresql+pg8000://` へ書き換え、末尾に `?sslmode=require` を足す。

**`sslmode` を付けること。** 付けないと暗号化なしで公衆網へ出る。pg8000 は `sslmode` を
引数として受け取れないため、アプリ側で `ssl_context` へ翻訳している（未設定のまま
非ローカルへ繋ごうとすると起動時に警告が出る）。証明書まで検証するなら
`sslmode=verify-full&sslrootcert=<CAのパス>` が望ましい。`require` は暗号化のみで
検証しないため中間者攻撃を防げない。

#### 無料プランで気に留めること

- **7日間アクセスが無いと一時停止する。** 日次の取り込みがあるので通常は起こらない。
- **DB 500MB を超えると読み取り専用になる。** `scripts/db_size.py` で定期的に見る。

#### 移行手順

スキーマは alembic で作り、データだけを移す。

```bash
# 1. 移行先にスキーマを作る（接続の確認も兼ねる）
DATABASE_URL="<移行先>" python -m alembic upgrade head

# 2. データを移す（pg_dump は libpq なので sslmode をそのまま解釈する）
pg_dump --format=custom --no-owner --no-privileges --data-only \
  --exclude-table=alembic_version --file=pci.dump "<移行元のURL>"
pg_restore --no-owner --no-privileges --dbname="<移行先のURL>" pci.dump

# 3. 欠けが無いか突き合わせる（pg_restore は部分成功で終わることがある）
DATABASE_URL="<移行先>" python -m scripts.verify_migration --source "<移行元>"
```

**`--exclude-table=alembic_version`** が要る。手順1で alembic が現在の版を記録済みなので、
これを外さないと復元時に主キー衝突で失敗する。

**`--disable-triggers` は要らない。** `pg_restore` はテーブルのデータを依存関係の順に流す
（`race_entries` は `races` の後）ので外部キーは壊れない。むしろ `--disable-triggers` は
外部キーの内部トリガーを止めるため superuser が要り、マネージド Postgres では拒否される。

上記は実際の PostgreSQL 16 に対して通し、`verify_migration` が一致を返すことを確認した手順。

**`pg_dump` が手元に無い場合はコンテナの中のものを使う。** 開発用DBは
`postgres:16-alpine`（`docker-compose.yml`）なので、移行元と同じ版が入っている。

```bash
docker compose exec db pg_dump -U pci -d pci_dev --format=custom \
  --no-owner --no-privileges --data-only --exclude-table=alembic_version -f /tmp/pci.dump

docker compose exec -e PGPASSWORD="<移行先のパスワード>" -e PGSSLMODE=require db \
  pg_restore -h <移行先のホスト> -p 5432 -U <移行先のユーザー> -d postgres \
  --no-owner --no-privileges /tmp/pci.dump
```

#### 容量の運用

`model_version` は主キーの一部なので、世代を上げると行が**更新ではなく追加**される。
放置するとコアデータより速く容量を食う。

```bash
python -m scripts.db_size                     # 現在の容量と世代別行数
python -m scripts.prune_mart_versions         # 削除対象を確認（DBは変更しない）
python -m scripts.prune_mart_versions --apply # 実際に削除
```

手元で本番と同じイメージを動かす場合:

```bash
docker build -t pci-api apps/api
docker run -p 8000:8000 -e DATABASE_URL=... -e PUBLIC_API_TOKEN=... pci-api
```

**マイグレーションはイメージ側で自動実行しない。** 複数インスタンスが同時起動すると
競合するため、デプロイ手順で1回だけ流すこと。

```bash
alembic upgrade head
```

必ず設定する環境変数:

| 変数 | 未設定だとどうなるか |
|---|---|
| `DATABASE_URL` | ローカル既定を見に行き接続できない |
| `PUBLIC_API_TOKEN` | **`/api/v1/*` が無認証で全公開**（起動時に警告が出る） |
| `INGEST_TOKEN` | `/internal/ingest/*` が無認証 |
| `CORS_ALLOW_ORIGINS` | ローカル開発の2オリジンのみ許可（公開フロントからは弾かれる） |
| `RATE_LIMIT_TRUSTED_PROXIES` | **全利用者が同じキーへ集約され、実質「全体で120回/分」になる** |

レート制限は既定で 120回/分・クライアント単位（`RATE_LIMIT_PER_MINUTE=0` で無効）。
ロードバランサ配下では `RATE_LIMIT_TRUSTED_PROXIES` に段数を設定しないと、
接続元IPが常にプロキシになるため制限が全利用者で共有されてしまう。

CI はイメージのビルドと `/health` 応答までを毎回検証する（`docker` ジョブ）。
レジストリへの push は入れていない。デプロイ先が決まってから足すこと。

### web（Vercel）

ルートの `vercel.json` が設定を持つ。Vercel の環境変数へ次の2つを入れる。

| 変数 | 値 | 入れ忘れるとどうなるか |
|---|---|---|
| `API_BASE_URL` | Cloud Run のサービス URL | 開発用の `127.0.0.1:8000` へ接続を試み、全ページが接続エラーになる |
| `API_ACCESS_TOKEN` | API 側の `PUBLIC_API_TOKEN` と**同じ値** | 全リクエストが 401 になる |

どちらも「APIは正常なのに画面が壊れる」形で出るため、画面の案内文を原因別に
分けてある（`src/lib/apiError.ts`）。設定漏れなら設定を、値の不一致ならトークンの
突き合わせを促す。「APIが起動しているか確認」とは出ない。

### 手元で本番と同じイメージを動かす

```bash
docker compose --profile api up --build api
```
