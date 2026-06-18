# ADR-0003: モノレポ構成

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** @yamandesu44

---

## Context

以下の3コンポーネントを管理する必要がある:

- `apps/api/`: FastAPI バックエンド（Python, Linux）
- `apps/web/`: Next.js フロントエンド（TypeScript, Vercel）
- `apps/ingestion-worker/`: JV-Link取り込みワーカー（Python, Windows）

また、OpenAPI 生成のTypeScript型をフロントエンドと共有したい。

選択肢:
1. ポリレポ（各コンポーネント別リポジトリ）
2. **モノレポ（採用）**

---

## Decision

**モノレポ**を採用する。

```
pci_app/
├── apps/
│   ├── api/                      # FastAPI + Python
│   │   ├── src/pci/
│   │   ├── tests/
│   │   ├── alembic/
│   │   └── pyproject.toml
│   ├── web/                      # Next.js + TypeScript
│   │   ├── src/{app,features,components,lib}/
│   │   └── package.json
│   └── ingestion-worker/         # Python, Windows 専用
│       ├── src/
│       ├── fixtures/
│       └── pyproject.toml
├── packages/
│   └── api-client/               # OpenAPI 生成 TS 型・クライアント（web 共有）
├── docs/
│   ├── adr/
│   ├── domain/
│   └── design/
├── CLAUDE.md
├── docker-compose.yml            # ローカル PostgreSQL 等
└── README.md
```

### CI 戦略

- `apps/api/**` の変更 → Python CI（mypy / ruff / pytest）を実行
- `apps/web/**` の変更 → Node CI（tsc / eslint / vitest）を実行
- `packages/api-client/**` の変更 → 両方の CI をトリガー
- パスフィルタリングで不要なジョブを省略

### API 型共有フロー

```
FastAPI (apps/api) → OpenAPI spec (openapi.json)
    → packages/api-client (openapi-typescript 等で生成)
    → apps/web で import
```

---

## Consequences

**ポジティブ:**
- APIスキーマ変更がフロントエンドに即座に型レベルで反映される
- ドキュメント・ADRが一箇所に集約される
- 横断的な変更が1PRで完結する

**ネガティブ:**
- Python（pyproject.toml）と Node（package.json）のツールチェーンが混在する
- リポジトリが大きくなるにつれてCIが複雑化する可能性

**緩和策:**
- CI はパスフィルタリングで無駄な実行を防ぐ
- `ingestion-worker` は Windows 専用のため、CI でのテスト実行は fixtures ベースに限定
