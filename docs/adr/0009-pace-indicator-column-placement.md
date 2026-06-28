# ADR-0009: ペース指標カラムの配置 — core 層への confirmed PCI 埋め込みと mart 層の版管理分離

- **Status:** Accepted
- **Date:** 2026-06-28
- **Deciders:** @yamandesu44

---

## Context

ADR-0006 で raw / core / mart の3層分離を決定した。ここで問題になるのが、
**PCI / RPCI / PCI3 の「確定値」をどの層に置くか**という配置の決断である。

PCI 等は JV-Link 原文そのものではなく、`pci.py` による算出値（派生データ）である。
以下の2択が考えられる:

**案 A — mart 専用:** すべての PCI 値を mart 層のみに置き、`formula_version` を必須属性とする。  
**案 B — core 埋め込み:** 確定後の PCI 実績値 (`pci_actual`, `rpci_actual`, `pci3_actual`) を
core 層（`race_entries` / `races`）に直接持ち、`formula_version` の版管理は mart の補助テーブル
`pci_recalc` に委ねる。

---

## Decision

**案 B（core 埋め込み）** を採用する。

### 配置方針

| 値 | 配置 | 備考 |
|---|---|---|
| `race_entries.pci_actual` | **core** | 確定後・個馬PCI（`pci.py` 算出） |
| `races.rpci_actual` | **core** | 確定後・レース代表RPCI |
| `races.pci3_actual` | **core** | 確定後・上位3着馬 PCI 平均 |
| `predicted_pace.predicted_rpci` | **mart** | 出走前の想定RPCI（`model_version` 付き） |
| `pace_fit.pai` | **mart** | 展開合致スコア（`model_version` 付き） |
| `pci_recalc` | **mart** | 式変更時の旧・新 PCI 比較保存（`formula_version` 付き） |

### core に PCI 実績値を置く根拠

1. **クエリ効率:** バックテスト・統計集計は `race_entries JOIN races` の結合で
   PCI を参照するユースケースが多い。mart を経由する余計な JOIN を避けることで
   クエリが単純になり、パフォーマンスが向上する。

2. **確定値は「計算済みの事実」:** 確定後の PCI は結果データ（走破タイム・上がり3F）
   から一意に導かれ、時間が経っても値が変わらない。予測値とは性質が異なる。

3. **ドメインモデルとの整合:** `RecordRaceResultUseCase` が結果確定の責務を持ち、
   PCI 算出と `race_entry.pci_actual` への書き込みを同一トランザクションで行う。
   mart 専用にすると書き込み先が別テーブルに分散し、ユースケースの境界が曖昧になる。

### formula_version の管理方針

`pci_actual` には `formula_version` 列を持たせない。代わりに:

- **通常運用:** 式が変わったら `RecordRaceResultUseCase` を全確定レースに再実行し、
  `pci_actual` を最新式で上書きする（常に現行 `formula_version` の値を保持）。
- **式変更の記録・比較:** 旧式と新式の差を残したい場合は mart の `pci_recalc` に
  `(race_key, horse_no, formula_version, pci)` として両 version を保存する。
  コードコメント `# formula_version は mart 層で管理` がこの意図を示している。

```
通常参照経路:  race_entries.pci_actual （常に現行式の値）
式変更時の比較: pci_recalc WHERE formula_version IN ('pci-v1', 'pci-v2')
```

---

## Consequences

**ポジティブ:**
- `race_entries` / `races` のみで集計・バックテストが完結し、クエリが簡潔になる
- `RecordRaceResultUseCase` がレース確定の単一責務として PCI 算出・保存を完結できる
- mart の `predicted_pace` / `pace_fit` は予測固有の `model_version` 管理に集中できる

**ネガティブ:**
- `pci_actual` の隣に `formula_version` が存在しないため、
  「どの式で算出されたか」を記録から直接辿れない。
- 全確定レースに式変更の再実行が必要（数千〜数万レース規模になりうる）。

**緩和策:**
- 式変更時は `pci_recalc` に旧・新 version を両方保存してから `pci_actual` を更新する
  運用手順を定め、`formula_version` の切り替えログをバッチ実行記録として残す。
- `formula_version` の変更は ADR-0004 に従い、ゴールデンテスト更新と同時にコミットし、
  変更根拠をコミットメッセージに記載する。

**将来の拡張:**
- ML モデルが本番化し式変更の頻度が上がった場合は、
  mart 専用テーブル（案 A）への移行を再検討する（`pci_recalc` がすでにその準備状態）。
