# 設計書 02: DDDドメインモデル

## 1. 境界づけられたコンテキスト

| コンテキスト | 責務 | 中核度 |
|---|---|---|
| **Data Acquisition** | JV-Link取得・固定長パース・正規化投入（別プロセス、ADR-0002） | 高（技術的） |
| **Racing Data** | Race / RaceEntry / Horse / Jockey / Trainer マスタの正規モデル | 中 |
| **Pace Analysis** ★ | PCI / RPCI / PCI3 / 脚質 / PAI（ドメインの王冠） | 最高 |
| **Forecast** | 未確定レースへの予測適用・展開シナリオ・説明生成 | 高 |
| **Presentation** | API / BFF・可視化向けDTO | 中 |

---

## 2. レイヤー構造（apps/api）

```
domain/          ← 外部依存ゼロ（標準ライブラリのみ）
  shared/        VO: RaceKey, Distance, RaceTime, Furlong3Time, CornerPositions, Reason
  racing/        Race, RaceEntry, Horse エンティティ
  pace/          PciCalculator, RunningStyleClassifier, RpciForecaster, PaceAdaptabilityScorer
application/     ユースケース（domain のみ参照）
infrastructure/  SQLAlchemyモデル, Repository実装, DI（application/domain 参照）
presentation/    FastAPI routers, Pydanticスキーマ（application/domain 参照）
```

依存方向は ADR-0001 で厳守。`domain` は SQLAlchemy / Pydantic / FastAPI を import しない。

---

## 3. 値オブジェクト（VO）

すべて不変（frozen dataclass / NamedTuple）・コンストラクタで自己検証。

| VO | 内容 | 検証例 |
|---|---|---|
| `RaceKey` | 16桁レース識別子 | 桁数・各構成要素の範囲 |
| `Distance` | 距離(m) | 正の値・現実的範囲 |
| `RaceTime` | 走破タイム(秒) | 正の値 |
| `Furlong3Time` | 上がり3F(秒) | 正の値・走破タイム未満 |
| `CornerPositions` | 1〜4角通過順位 | 1以上・頭数以下 |
| `PCI` | PCI値 + `formula_version` + `reasons` | — |
| `RunningStyle` | 脚質(逃/先/差/追/自在) + 信頼度 + `reasons` | — |
| `RPCI` | RPCI値 + 種別(実績/想定) | — |
| `PAIScore` | 0〜100 + `reasons`(減点内訳) | 0〜100範囲 |
| `Reason` | 説明可能性の要素（要因コード + 寄与 + 説明文） | — |

---

## 4. エンティティ・集約

### Race（集約ルート）
- `RaceKey`, 距離, コース（競馬場・芝/ダ）, 馬場状態, 天候, グレード, クラス
- 出走馬群（`RaceEntry`）
- 確定後: ラップタイム, 実績RPCI, PCI3

### RaceEntry
- 馬番, 枠, `Horse`参照, 斤量, 騎手, 調教師
- 確定後: 着順, 走破タイム, 上がり3F, 通過順位(1〜4角), PCI, 脚質

### Horse（集約ルート）
- 血統登録番号(ketto_num), 馬名, 性, 生年
- 過去走の PCI / 脚質履歴

---

## 5. ドメインサービス（純粋関数中心＝説明可能・テスト容易）

### PciCalculator（`pace/pci.py`）
走破タイム・上がり3F・距離 → PCI。**式の唯一の真実の場所**（ADR-0004）。

### RunningStyleClassifier（`pace/running_style.py`）
過去5走の4角通過順位＋頭数 → 脚質＋信頼度（C9の暫定ルール、閾値は設定化）。

```
番手率を計算し、
  逃げ: 1〜2番手率 ≥ 60%
  先行: 3〜5番手率 ≥ 60%
  差し: 6〜9番手率 ≥ 60%
  追込: 10番手以降率 ≥ 60%
  いずれも未満 → 自在
信頼度 = 該当番手率（説明可能性として reasons に格納）
```

### RpciForecaster（`pace/rpci_forecast.py`・戦略IF）
出走馬の脚質構成・距離・コース・馬場・履歴 → 想定RPCI + 信頼度 + reasons。
- MVP: `RuleBasedRpciForecaster`（rule-v1）
- 将来: `LgbmRpciForecaster`（lgbm-v*）
- 詳細は ADR-0005

### PaceAdaptabilityScorer（`pace/adaptability.py`）
想定RPCI + 各馬脚質 + 過去類似ペース実績 → PAI + 合致ラベル + reasons。

```
PAI = 100 − RPCI差補正 − 距離補正 − 馬場補正   （C10、重みは設定ファイル）
  RPCI差補正: 馬の好ペースと想定RPCIの乖離に対する減点
  距離補正  : 距離適性の乖離に対する減点
  馬場補正  : 馬場適性の乖離に対する減点
各減点は Reason として保持（説明可能性）
```

---

## 6. 説明可能性の貫通

`Reason`（要因コード・寄与・説明文）を VO/結果に持たせ、application → presentation → API → UI まで一貫して伝播させる。
ML導入後は SHAP 寄与を同じ `Reason` 構造に載せる（インターフェース不変）。

---

## 7. アプリケーションサービス（ユースケース例）

| ユースケース | 概要 |
|---|---|
| `AnalyzeRacePace` | 確定レースの各馬PCI・実績RPCI・PCI3を算出（mart更新） |
| `ForecastRace` | 未確定レースの想定RPCI・展開シナリオ・PAI・合致馬を生成（mart更新） |
| `GetRaceForecast` | mart から予想結果を取得しDTO化（API用） |
| `GetHorsePaceHistory` | 馬のPCI/脚質履歴を取得 |

各ユースケースは Repository インターフェース（domain/application定義）に依存し、実装はinfrastructure。
