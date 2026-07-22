# pci-api — 競馬展開予想 SaaS バックエンド

FastAPI + SQLAlchemy + Alembic によるレイヤードDDD（domain / application / infrastructure / presentation）。

## セットアップ

```bash
cd apps/api
pip install -e ".[dev]"
cp .env.example .env          # DATABASE_URL を設定
docker-compose -f ../../docker-compose.yml up -d db
alembic upgrade head          # スキーマ適用
```

## 開発サーバ起動

```bash
uvicorn pci.presentation.app:app --reload
# Swagger UI: http://127.0.0.1:8000/docs
```

## 主要エンドポイント（/api/v1）

| メソッド | パス | 概要 |
|---|---|---|
| GET | `/health` | ヘルスチェック |
| GET | `/api/v1/races/{race_key}/forecast` | 展開予想（想定RPCI・展開シナリオ・各馬 PAI・展開コメント） |
| GET | `/api/v1/races/{race_key}/pace-analysis` | 確定後ペース分析（各馬PCI・実績RPCI・PCI3・回顧コメント・formula_version） |
| GET | `/api/v1/races/{race_key}` | レース詳細（出走馬・確定指標 RPCI/PCI3） |

`race_key` は16桁数字（不正値は 422、未登録レースは 404）。
`pace-analysis` は確定後（status=result）のみ。確定前のレースは 409 を返す。
`forecast` / `pace-analysis` は指標を自然文へ翻訳した `comment`（model_version=comment-v2・
ADR-0008）を含み、生成根拠を `reasons` で説明する。

### Gemini 展開コメント（任意）

既定の`COMMENT_GENERATOR_MODE=rule`では、APIキーが環境に残っていても外部APIを呼ばず、
決定論的な`comment-v2`を使用する。Geminiは`COMMENT_GENERATOR_MODE=gemini`と
`GEMINI_API_KEY`の両方を明示した場合だけ有効になる。既定モデルは`gemini-3.5-flash`で、
必要な場合だけ`GEMINI_MODEL`で変更できる。APIキー未設定、またはGemini APIの呼び出しに
失敗した場合は`comment-v2`へフォールバックする。

```dotenv
COMMENT_GENERATOR_MODE=gemini
GEMINI_API_KEY=your-api-key
# GEMINI_MODEL=gemini-3.5-flash
```

Gemini APIの無料枠・課金条件・提供モデルはGoogle側で変更される可能性があるため、運用前に
[公式料金表](https://ai.google.dev/gemini-api/docs/pricing?hl=en)と
[モデル情報](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash)を確認する。
**外部API費用を確実にゼロにする運用では`COMMENT_GENERATOR_MODE=rule`を維持する。**
この場合も`comment-v2`で展開コメント機能は利用できる。

## テスト

```bash
python -m pytest tests/unit/ tests/contract/   # 高速・DB不要（ドメイン/アプリ/API契約）
python -m pytest tests/integration/            # testcontainers-postgres（要 Docker）
python -m mypy src/ --strict                   # 型チェック（`python -m` 必須。素の mypy/pytest は
                                                # 隔離環境を指し得るため fastapi 等が見つからないエラーになる場合あり）
ruff check src/ tests/                         # Lint
lint-imports                                   # レイヤー依存方向の検証
```

## 能力重みの実DB比較

Phase 2の`AbilityWeights`候補を同じ確定レースで比較する。現行重みは自動変更しない。

```bash
python -m scripts.backtest_forecast \
  --date-from 2025-07-01 --date-to 2026-06-30 \
  --limit 2000 --sample-every 5 \
  --compare-ability-weights \
  --output results/ability-weights.json
```

比較対象は現行、近走内容のみ、近走重視、市場支持重視の4候補。出力は1位馬勝率・
1位馬好走率・TOP3好走捕捉率と現行差。異なる期間で改善が再現した場合のみ、
`AbilityWeights`の変更を別タスクで判断する。

2026-07-22に2025年後半212レース・2026年前半97レースで比較し、全3指標が両期間で
改善する候補は無かったため、現行重みを維持した。

### LightGBMモデルの改行

`models/*.txt`は内部の`tree_sizes`にバイト長を保持するため、必ずLFで扱う。
`.gitattributes`でWindows checkout時のCRLF変換を禁止している。モデルを追加する場合も
この属性の対象内へ配置し、`test_lgbm_forecaster.py::TestCommittedModels`を実行すること。
既存cloneにCRLFファイルが残っていても、ローダーがLFへ正規化してから読み込む。

## レイヤー構成（依存は一方向・import-linter で強制）

```
presentation (FastAPI)  →  application (UseCase)  →  domain (PCI/RPCI/PAI/脚質)
infrastructure (SQLAlchemy/Repository)  →  application, domain
```

予測ロジックは戦略IF `RpciForecaster`（既定 rule-v1）で注入し、将来の ML 実装へ
アプリ側無変更で差し替え可能（ADR-0005）。
