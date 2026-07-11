# AGENTS.md — OpenAI Codex 向けプロジェクト指示

このファイルは **OpenAI Codex** がこのリポジトリで作業する際の入口です。
Claude Code とプロジェクトルールを共有するため、**共通ルールは `docs/PROJECT_RULES.md` を正**とします。
このファイルには Codex 固有の運用だけを書きます（ルールの二重管理・食い違いを避けるため）。

---

## 作業開始前に必ず読むファイル（この順）

1. `docs/HANDOFF.md` — 現在の作業状態・最新コミット・次にやること・テスト状況
2. `docs/PROJECT_RULES.md` — Claude Code と共通の遵守ルール（**最重要**）
3. `tasks/current.md` — 進行中タスク
4. `docs/SPEC.md` — 確定仕様と未確定事項の区別
5. `docs/ARCHITECTURE.md` — システム構成
6. 必要に応じて `docs/adr/`, `docs/design/`, `docs/DECISIONS.md`

`CLAUDE.md` は Claude Code 固有指示だが、ユビキタス言語表・PCI 式管理・DoD など
プロジェクト共通の詳細も含む。参考として目を通してよい（矛盾時は PROJECT_RULES を優先）。

---

## 守ること（Codex 固有の運用）

- **ルール本体は `docs/PROJECT_RULES.md`**。ここを読まずに実装しない。
- **未確認の仕様・式・係数を推測で確定しない。** 不明点は `docs/SPEC.md` の「未確定事項」へ記録し、
  実装は暫定と明記する（独断で正式仕様化しない）。
- **既存コードの設計方針に従う**（レイヤードDDD・式の隔離・表示/解析の分離）。周辺コードと読み口を揃える。
- **UI に PCI/RPCI 実数値を出さない**（PROJECT_RULES §5）。言葉・段階評価へ翻訳する。
- **JV-Data/CP932 のバイト位置を変える時は根拠と検証結果を残す**（PROJECT_RULES §6）。
- 秘密情報（SID・DBパスワード・APIキー）をコード・ログ・コミットに含めない。

---

## テスト・型・Lint（実装したら必ず実行）

```bash
# API（Python）
cd apps/api
pytest tests/unit/ tests/contract/ -q
ruff check src/ tests/
lint-imports                                  # 依存方向（domain 外部依存禁止）
mypy src/pci/domain/ src/pci/application/ --strict   # domain+application は 0 エラーが基準

# Web（TypeScript）
cd apps/web
npm run test
npm run typecheck
```

注意:
- `mypy src/ --strict` を全体にかけると infrastructure/presentation で SQLAlchemy/Pydantic/FastAPI の
  スタブ未導入エラーが多数出る（**環境要因・コード欠陥ではない**）。domain/application を対象に確認する。
- API スキーマを変えたら `cd apps/api && python scripts/export_openapi.py` で
  `packages/api-client/openapi.json` を再生成し、契約テストを通す。

---

## 作業中断・終了時の手順（Codex → 次の担当へ）

1. `docs/HANDOFF.md` を更新（更新日時 / 担当AI=Codex / 最新コミット / 完了・作業中・次の作業 /
   変更対象ファイル / 未解決事項 / テスト状況）。
2. `tasks/current.md` のチェックボックス・状態を更新。未着手の発見事項は `tasks/backlog.md` へ。
3. 設計判断をしたら `docs/DECISIONS.md`（重い決定は `docs/adr/`）、仕様の確定/未確定変化は `docs/SPEC.md` に反映。
4. テスト・型・Lint を実行し、結果を HANDOFF に記録。

---

## コミット方針（Codex 固有）

- 共通のコミット規約は `docs/PROJECT_RULES.md` と `CLAUDE.md` の方針に合わせる
  （Conventional Commits 準拠・スコープ付き・日本語/英語いずれも可だが1コミット1論点）。
- Codex がコミットする場合は、コミットメッセージ本文に担当が Codex であることを識別できる
  トレーラを付けてよい（例: `Co-Authored-By: Codex <codex@openai.com>`）。
  Claude Code 側のセッション識別子など、他ツール固有のトレーラは流用しない。
- ブランチは指定がなければ現行の作業ブランチ（`docs/HANDOFF.md` の「ブランチ」）を使う。
  勝手に別ブランチへ push しない。
- 破壊的・外部影響のある操作（force push・PR 作成・外部送信）はユーザーの明示指示があるまで行わない。
