# PROJECT_RULES — Claude Code / Codex 共通ルール

このファイルは **Claude Code と OpenAI Codex の両方が守る単一の共通ルール**です。
`CLAUDE.md`（Claude Code 向け）と `AGENTS.md`（Codex 向け）は、このファイルを
参照し、各ツール固有の指示だけをそれぞれに記載します。ルールが食い違ったときは
**このファイルを正**とします。

---

## 1. プロジェクトの目的

JRA-VAN DataLab（JV-Link）由来の競馬データを元に、レース展開（ペース・脚質適性）を
自動分析する SaaS。

**コアバリュー:** 「PCI を理解していない競馬ファンでも展開予想を活用できること」。
TARGET の完全再現ではなく、上級者の暗黙知（展開判断・展開合致馬抽出）を
**説明可能なアルゴリズム**に変換することが目的。

用語は必ず `docs/domain/ubiquitous-language.md` と `CLAUDE.md` のユビキタス言語表に
統一する（PCI / RPCI / PCI3 / 脚質 / PAI / 想定RPCI / 展開合致馬 / 展開コメント など）。

---

## 2. コーディング規約

### 共通
- ユーザー向け出力・ドキュメント・コードコメントは **日本語**。
- コメントは「WHY（なぜそうするか）」が非自明なときのみ書く（自明な説明は書かない）。
- 既存コードの設計方針・命名・粒度に合わせる。周辺コードと読み口が揃うように書く。

### Python（apps/api, apps/ingestion-worker）
- 型ヒント 100%、`mypy --strict` を基準とする。
- Ruff（linter + formatter）。ルール: `E, F, I, N, UP, B, SIM`、line-length 100。
- domain 層は**純粋 Python・標準ライブラリのみ**（SQLAlchemy / Pydantic / FastAPI を import しない）。
  import-linter でCI強制（`pci.presentation → infrastructure → application → domain` の一方向）。
- 値オブジェクト（VO）は不変（frozen dataclass / NamedTuple）・コンストラクタで自己検証。
- すべての算出結果に `reasons: list[Reason]` を付ける（説明可能性の原則）。

### TypeScript（apps/web）
- `tsc --noEmit` が通ること。API 型は `@pci/api-client`（OpenAPI 生成）を使い、手書き複製しない。
- 解析ロジックとユーザー向け表示ロジックを分離する（`lib/pace.ts` 等が翻訳層）。

---

## 3. 命名規則

- Python: モジュール/関数/変数 `snake_case`、クラス `PascalCase`、定数 `UPPER_SNAKE`。
- TypeScript: 変数/関数 `camelCase`、コンポーネント/型 `PascalCase`、コンポーネントファイルは `PascalCase.tsx`。
- バージョン識別子: 計算式は `formula_version`（例 `pci-v2`）、予測/生成器は `model_version`
  （例 `rule-v4`, `pai-v1`, `comment-v1`, `lgbm-*`）。**mart 層の算出結果には必ず付与する**。

---

## 4. ディレクトリ構成の基本方針

```
apps/api/src/pci/
  domain/        外部依存ゼロ。VO・エンティティ・pace 計算核（pci/running_style/rpci_forecast/adaptability/affinity/commentary）
  application/   ユースケース（domain のみ参照）
  infrastructure/ SQLAlchemy・Repository 実装・DI
  presentation/  FastAPI routers・Pydantic schemas
apps/web/src/    app（App Router）/ components / lib（表示ロジック・API クライアント）
apps/ingestion-worker/src/ingestion/  JV-Link/mykeibadb 取り込み・固定長パーサ
packages/api-client/  OpenAPI 生成 TS 型
docs/            adr / design / domain + 本引き継ぎ基盤
tasks/           current.md / backlog.md
```

新規コードは対応する層に置く。層をまたぐ責務の混在を避ける。

---

## 5. UI に表示してよい情報・してはいけない情報（最重要・プロダクト固有）

本プロジェクトは競馬の展開予想・適性分析アプリ。**内部の実数値をそのまま出さないこと**が
コアバリューに直結する。

**表示してはいけない（一般ユーザー向け画面・初心者向け解説）:**
- PCI / PCI3 / RPCI などの**実数値**（例: 「RPCI 53.2」）。
- 内部の閾値・係数・生の指標名を前面に出すこと。

**表示してよい:**
- 段階評価・分かりやすい言葉への変換（例: 「やや落ち着いた流れ」「高相性」「展開が向く」）。
- 想定展開・展開恩恵馬・評価を下げたい馬・展開の信頼度（言葉/バー/色で表現）。
- 実数値を出す場合は Accordion 等の「詳細データ」に隔離し、初心者に最初から見せない。

**原則:** 解析ロジック（実数値を扱う）と表示ロジック（言葉に翻訳する）を分離する。
翻訳は主に web の `lib/pace.ts` と API の `commentary.py`（展開コメント）が担う。

---

## 6. 競馬データ固有のルール

- PCI / RPCI / PCI3 の計算式は `apps/api/src/pci/domain/pace/pci.py` **だけ**に書く（ADR-0004）。
  他所からは呼び出しのみ。式変更時は**ゴールデンテスト更新**と `formula_version` 更新を必須とし、
  変更根拠をコミットメッセージに残す。
- **仕様未確定の計算式・係数・閾値を独断で確定しない**（PAI 定義・脚質判定ルール等は暫定）。
  暫定値は設定（`RuleWeights` / `PaiWeights` 等）で調整可能にし、`model_version` で前進する。
- 各馬の過去好走時データから、展開への合致度・得意なレース質を評価する（affinity/adaptability）。
- JV-Data / CP932 固定長データの**バイト位置を変更する場合は、根拠と検証結果を残す**
  （実データでの確認日・レース・オフセットをコード near か handoff に明記。`jv_spec.py` が真実の場所）。
- JRA-VAN 関連データは**生データ再配布禁止前提**。公開するのは独自指標・分析結果のみ。
- 取り込みスコープ: JRA 中央競馬のみ・日次バッチ。認証情報（SID・DBパスワード）は `.env` 管理・非コミット。

---

## 7. テスト方針

| 層 | 手段 | 目標 |
|---|---|---|
| domain（pace 核） | pytest 単体 + **ゴールデンテスト** + プロパティテスト(hypothesis) | 95%+ |
| application | Fake Repository 使用の単体テスト | 80%+ |
| infrastructure | testcontainers-postgres 統合テスト | 主要パス |
| presentation | FastAPI TestClient + スキーマ契約テスト | 主要エンドポイント |
| web | vitest（表示ロジック lib/*） | 主要変換 |

- 新機能・バグ修正には必ずテストを追加する。回帰バグは再現テストを先に用意する。
- API スキーマを変えたら `packages/api-client/openapi.json` を再生成し、契約テストを通す
  （`cd apps/api && python scripts/export_openapi.py`）。

---

## 8. エラーハンドリング方針

- ドメインの不正入力は VO/ユースケースで早期に検出し、意味のある例外/理由を返す。
- 外部データ（JV-Data / mykeibadb）の異常値は**取り込み側で弾く**（例: 上がり3F の妥当範囲チェック）。
  壊れた1件でパイプライン全体を止めない。スキップ時はログに残す。
- バッチは成功/失敗を `ingest_log` に記録し、失敗時は通知（`NOTIFY_WEBHOOK_URL`）できる構成にする。

---

## 9. ログ・機密情報

- API キー・SID・DB 接続文字列・パスワードを**ログにも出力しない**。`.env` 管理・`.gitignore` 済み。
- 内部の生指標値（PCI/RPCI 等）を、ユーザーの目に触れる場所（UI・ユーザー向けログ）に
  不用意に出さない（第5節と同じ原則を運用ログにも適用）。
- コミットに生データ・認証情報を含めない。

---

## 10. 不明点・仕様変更の扱い

- **不明点を独断で仕様化しない。** 未確認の仕様・式・数値は推測で確定せず、
  `docs/SPEC.md` の「未確定事項」に記録し、実装は暫定であることを明示する。
- 仕様変更・設計判断をしたら記録する:
  - アーキ/技術選定/データ契約/式・モデル方針など重い決定 → **ADR**（`docs/adr/NNNN-*.md`, MADR 形式）。
  - それ以外の設計判断 → `docs/DECISIONS.md`。
  - 確定/未確定の仕様の変化 → `docs/SPEC.md`。
- 「実装されている」ことは「正式仕様である」ことを意味しない。両者を常に区別する。

---

## 11. Definition of Done（共通）

- [ ] 型ヒント 100% / `python -m mypy src/ --strict` で全体0エラー（`mypy`は必ず`python -m`経由。
  素の`mypy`コマンドは環境によって隔離venvを指しfastapi等が「見つからない」誤検知になり得る）
- [ ] Ruff 0 エラー / web は `tsc --noEmit` clean
- [ ] pytest / vitest green（新機能・修正にテスト追加）
- [ ] domain 層に外部依存なし（import-linter KEPT）
- [ ] 算出結果に `reasons` 付き（説明可能性）
- [ ] mart 層の結果に `model_version` または `formula_version` を記録
- [ ] UI に内部実数値を露出していない（第5節）
- [ ] 生データ・認証情報がコミット・ログに含まれていない
- [ ] 中断/終了時に `docs/HANDOFF.md` と `tasks/current.md` を更新した
