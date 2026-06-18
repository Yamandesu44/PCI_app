# 設計書 04: API設計

- FastAPI / `/api/v1`。OpenAPI を自動生成し `packages/api-client` で Next.js に型共有。
- **生データは公開しない**（C2）。独自指標・分析結果のみDTOで返す。
- 認証は MVP では無効。ただし**認証ミドルウェアの差込口**を確保（C11）。

---

## 1. エンドポイント一覧

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/v1/races?date=&jyo=&grade=` | レース一覧 |
| GET | `/api/v1/races/{race_key}` | レース詳細（出馬表 or 結果） |
| GET | `/api/v1/races/{race_key}/forecast` | **想定RPCI・展開シナリオ・展開合致馬(PAI)・根拠**（中核） |
| GET | `/api/v1/races/{race_key}/pace-analysis` | 確定後: 各馬PCI・実績RPCI・PCI3 |
| GET | `/api/v1/horses/{ketto_num}/pace-history` | PCI/脚質履歴 |
| GET | `/api/v1/health` | ヘルスチェック |
| POST | `/api/v1/internal/ingest` | 内部・要トークン認証。ingestion-worker からの投入 |

---

## 2. 中核レスポンス: `/forecast`

説明可能性を最優先し、すべての判定に `reasons` を付与。`model_version` を必ず返す。

```jsonc
{
  "race_key": "2026061406030811",
  "predicted_rpci": {
    "value": 53.2,
    "label": "ややスロー",
    "confidence": 0.7,
    "reasons": [
      "逃げ2・先行5で前半が緩む傾向",
      "中山1600mは例年スロー寄り"
    ]
  },
  "pace_scenario": {
    "type": "slow",
    "lead_horses": [3, 7],
    "diagram": { "front": [3, 7], "mid": [1, 5], "rear": [2, 9] }
  },
  "fit_horses": [
    {
      "horse_no": 5,
      "running_style": "差し",
      "pai": 78,
      "label": "恩恵",
      "reasons": [
        "想定スローでも上がり最速圏の実績",
        "距離・馬場とも適性内"
      ]
    }
  ],
  "model_version": "rule-v1"
}
```

---

## 3. 共通方針

| 項目 | 方針 |
|---|---|
| エラー形式 | RFC 9457（problem+json）推奨。統一エラーハンドラ |
| バージョニング | URL パスで `/api/v1`。破壊的変更時に v2 |
| ページング | 一覧系は limit/offset または cursor |
| 説明可能性 | 判定系レスポンスは必ず `reasons` を含む |
| version 露出 | 予測系は `model_version`、PCI系は `formula_version` を返す |
| 生データ非公開 | core/mart の生値を直接返さずDTO変換（C2） |
| 認証差込口 | FastAPI dependency でミドルウェアを差し込めるようにする（MVPはno-op） |
| 内部API保護 | `/internal/*` はトークン認証必須（ingestion-worker専用） |

---

## 4. 型共有フロー

```
FastAPI → OpenAPI spec (openapi.json)
  → packages/api-client（openapi-typescript で型生成）
  → apps/web で import（フロントとバックの型を一致）
```

---

## 5. 契約テスト

- presentation 層はスキーマスナップショットテストで後方互換を検知
- `packages/api-client` の型生成を CI で検証し、破壊的変更を可視化
