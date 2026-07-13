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
`forecast` / `pace-analysis` は指標を自然文へ翻訳した `comment`（model_version=comment-v1・
ADR-0008）を含み、生成根拠を `reasons` で説明する。

## テスト

```bash
python -m pytest tests/unit/ tests/contract/   # 高速・DB不要（ドメイン/アプリ/API契約）
python -m pytest tests/integration/            # testcontainers-postgres（要 Docker）
python -m mypy src/ --strict                   # 型チェック（`python -m` 必須。素の mypy/pytest は
                                                # 隔離環境を指し得るため fastapi 等が見つからないエラーになる場合あり）
ruff check src/ tests/                         # Lint
lint-imports                                   # レイヤー依存方向の検証
```

## レイヤー構成（依存は一方向・import-linter で強制）

```
presentation (FastAPI)  →  application (UseCase)  →  domain (PCI/RPCI/PAI/脚質)
infrastructure (SQLAlchemy/Repository)  →  application, domain
```

予測ロジックは戦略IF `RpciForecaster`（既定 rule-v1）で注入し、将来の ML 実装へ
アプリ側無変更で差し替え可能（ADR-0005）。
