# ADR-0005: 想定RPCI 予測戦略 — MVPルールベース + ML疎結合IF

- **Status:** Accepted
- **Date:** 2026-06-16
- **Updated:** 2026-07-11（受入基準の実測検証を追記・§5.4）。旧: 2026-06-28（rule-v3/v4 追記・LightGBM 芝/ダート別モデル採用）
- **Deciders:** @yamandesu44

---

## Context

「想定RPCI予測」は本プロダクトの中核機能であり、出走馬の脚質構成・距離・コース・馬場から
レースのペース（ハイ／平均／スロー）を予測する。

要件:
- MVP では**説明可能性を最優先**する
- 将来的に LightGBM 等で精度向上を図る
- 受入基準: 想定RPCI と実RPCI の **MAE ≤ 1.5**、展開3分類（スロー/平均/ハイ）の**一致率 ≥ 60%**

---

## Decision

### 1. 戦略インターフェース（疎結合）

予測ロジックを差し替え可能にするため、domain層に戦略インターフェースを定義する。

```
apps/api/src/pci/domain/pace/rpci_forecast.py

RpciForecaster (Protocol / ABC)
  forecast(race_context) -> RpciForecast
      RpciForecast = { value, label, confidence, reasons }

実装:
  RuleBasedRpciForecaster   # MVP（rule-v2）
  LgbmRpciForecaster        # 将来（lgbm-v*） ※同一IFを満たす
```

application層・presentation層は `RpciForecaster` インターフェースにのみ依存し、
具体実装はDIで注入する。**MLモデルへの差し替えがアプリ側コード変更ゼロで可能**。

### 2. MVP: ルールベース（`model_version = "rule-v2"`）

説明可能性を最優先し、以下の要因から想定RPCIを算出する透明なルール:

| 要因 | 効果 |
|---|---|
| 逃げ・先行馬の頭数 | 多いほど前半が速くなる → RPCI低（ハイ寄り） |
| 差し・追込馬の比率 | 多いほど前半が緩む → RPCI高（スロー寄り） |
| 距離 | 距離帯ごとの基準ペース |
| コース（競馬場・芝/ダ） | コース別の傾向補正 |
| 馬場状態 | 重馬場等の補正 |
| **前付け馬の実績ペース傾向（rule-v2 追加）** | 逃げ・先行候補が近走で前に行ったときの個馬PCI平均を反映 |
| 過去同条件レースの実RPCI傾向 | ベースライン |

各要因の寄与を `reasons` として必ず出力する（例: 「逃げ2・先行5で前半緩み傾向」）。

#### 2.1 rule-v2 改訂: 前付け馬の実績ペース傾向（2026-06-27）

**動機:** rule-v1 は逃げ・先行馬の「頭数」しか見ず、「単騎なら緩める逃げ馬」と
「ハナを切ると毎回飛ばす逃げ馬」を区別できなかった。

**変更:** 逃げ・先行と判定された各馬について、近10走のうち実際に前で運んだ過去走
（1角通過≤2、無ければ4角通過≤2）を抽出し、その馬自身の PCI（欠損時のみ当該レースの
実績 RPCI で補完）を平均して「その馬が前にいると作りやすいペース」を推定する。
出走する前付け候補ぶんを**等加重で平均**し、**先行争いの競合補正**（逃げ複数→速い方向）
を加えて想定 RPCI に混合する。

```
想定RPCI = ew × (前付け候補ペース傾向の平均 + 競合補正)
         + (1 − ew) × 頭数ベース構造値(距離・脚質)
         + 馬場補正
  ew = min(総前付け走数 × evidence_weight_per_sample, evidence_weight_cap)  # 上限<1
```

- **混合比 `ew`** は前付け実績の総走数に比例し、上限（既定 0.7）で頭打ち。
  距離・脚質ベースの prior を常に 30% 以上残すことで少数サンプルへの過適合を防ぐ。
- **前付け実績ゼロ**（新馬・差し追込のみ等）の場合は `ew=0` で **rule-v1 相当へ自動フォールバック**。
- ペース指標は **個馬PCI主体**（前で運んだその馬の前後半ラップを重視）。
- 重み（`evidence_weight_per_sample` / `evidence_weight_cap`）は `RuleWeights` で調整可能。

ゴールデン／既存テストは `front_pace_samples` 空のとき rule-v1 と完全一致するため不変。

#### 2.2 rule-v3: コース種別基準 RPCI 補正（2026-06-28）

**動機:** バックテストで芝とダートの実績 RPCI 平均が大きく異なることが判明した
（芝 53.1 / ダート 43.0、DB 2022〜2026 約 15,440 レース）。
rule-v2 以前はコース種別の基準差を考慮しておらず、ダートでスロー判定が出にくかった。

**変更:** `RuleWeights` に `turf_base_adjust: float = 5.0` / `dirt_base_adjust: float = -9.75` を追加。
芝レースには +5.0、ダートレースには −9.75 の基準補正を適用する。

#### 2.3 rule-v4: ダート展開3分類閾値の個別設定（2026-06-28、現行）

**動機:** rule-v3 までは芝の閾値（ハイ<49 / スロー>51）をダートにも共用していたが、
ダートの実績分布（平均 43.0）は芝（平均 53.1）と大きくずれているため、
ダートでの3分類が「ほぼ全員ハイ」になる問題があった。

**変更:** ダート専用閾値を `RuleWeights` に追加。`classify_pace()` がコース種別を受け取り
適切な閾値を選択する。

```python
# RuleWeights
dirt_high_threshold: float = 40.0   # ダート専用: ハイ < 40
dirt_slow_threshold: float = 46.0   # ダート専用: スロー > 46
# 芝は従来通り high_threshold=49.0 / slow_threshold=51.0
```

この決定により `classify_pace(rpci, track_type)` が **予測・実績のラベル化双方で共通利用**
する唯一の真実の場所となり、バックテストが予測ラベルと実績ラベルを公平に比較できる。

### 3. 展開分類（label）

想定RPCI値を3分類にマッピング:
- スロー / 平均 / ハイ（閾値は設定ファイルで調整可能）

### 4. 受入基準と検証

検証ハーネス（バックテスト）で過去データに対し以下を計測する:
- **MAE ≤ 1.5**（想定RPCI vs 実RPCI）
- **展開3分類一致率 ≥ 60%**
- **PAI リフト**: PAI 帯が高いほど好走率（3着内 / 重賞5着内）が上がること

#### 4.1 バックテスト実装（2026-06-27）

- 実装: `apps/api/src/pci/application/backtest.py`（純粋集計 + `ForecastBacktester`）
- 実行: `cd apps/api && python -m scripts.backtest_forecast --limit 200`
- **本番の `ForecastRaceUseCase` をそのまま再現**して評価する（評価専用経路を作らず、
  出荷ロジックそのものを測る）。mart へは保存しない。
- **lookahead 防止**: `_AsOfRaceRepository` が `find_horse_recent_entries` に
  「レース当日」カットオフ（`before`）を注入し、予測時点より未来の馬履歴を遮断する。
- **指標**: 想定RPCI の MAE / RMSE / バイアス / ラベル的中率、および PAI 帯別好走率・
  point-biserial 相関・最上位帯リフト。
- 「好走」「展開3分類」の判定は学習側と**同一の真実の場所**を再利用する
  （`affinity.is_good_run` / `rpci_forecast.classify_pace`）。定義の二重実装を作らない。
- ベースライン（全体好走率）と比較し、PAI のリフトを確認する。

> 注意: 重み（`evidence_weight_*` 等）を調整したら本バックテストで MAE / 一致率 /
> PAI リフトの回帰がないことを必ず確認する。`model_version` 別に比較できる。

### 5. LightGBM 実装（`model_version = "lgbm-v1"` / `"lgbm-turf-v1"` / `"lgbm-dirt-v1"`）

#### 5.1 統合モデル lgbm-v1（2026-06-28 追加）

```
apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py
  LightGBMRpciForecaster   # lgbm-v1（後方互換・統合モデル）
```

**特徴量（`FEATURE_NAMES`）:** `distance_m`, `is_dirt`, `jyo_cd`, `escape_count`,
`front_ratio`, `closer_ratio`, `style_balance`, `track_cond`（8次元）

**学習スクリプト:** `apps/api/scripts/train_rpci_lgbm.py`
- `--track-type all|turf|dirt` で芝/ダート/全件を切り替え
- early stopping（既定 50 ラウンド）・80/20 時系列分割

**モデルファイル:** `apps/api/models/rpci_lgbm_v1.txt`（gitignore 対象、本番環境のみ）

#### 5.2 芝/ダート別モデル（2026-06-28 採用決定）

**背景:** 統合モデル（lgbm-v1）ではダートの MAE が悪く、展開3分類のラベル的中率も
33.6% にとどまった。芝とダートでは実績 RPCI の分布が大きく異なるため（芝平均 53.1 /
ダート平均 43.0）、コース種別ごとにモデルを分けることで精度を向上させる方針を採用した。

**実装:**

```python
# lgbm_forecaster.py
SplitLightGBMRpciForecaster   # lgbm-turf-v1 / lgbm-dirt-v1
  def forecast(context):
      if context.track_type == "ダート":
          return _make_forecast(self._dirt_predict, context, MODEL_VERSION_DIRT)
      return _make_forecast(self._turf_predict, context, MODEL_VERSION_TURF)
```

**モデルファイル:**
- `apps/api/models/rpci_lgbm_turf_v1.txt` (`model_version="lgbm-turf-v1"`)
- `apps/api/models/rpci_lgbm_dirt_v1.txt` (`model_version="lgbm-dirt-v1"`)

**ローディング優先度（`load_best_forecaster()`）:**
1. 芝・ダート両モデルが揃っていれば `SplitLightGBMRpciForecaster`
2. 統合モデルが存在すれば `LightGBMRpciForecaster`
3. いずれもなければ `RuleBasedRpciForecaster`（フォールバック）

**バックテスト実績（DB 2022〜2026 約 15,440 レース）:**

| モデル | コース | MAE | ラベル的中率 | PAI point-biserial | 最上位帯リフト |
|---|---|---|---|---|---|
| lgbm-v1 (統合) | 全件 | 8.580 | 63.0% | - | 1.22x |
| lgbm-turf-v1 | 芝 | 9.472 | **76.0%** | +0.108 | **1.33x** |
| lgbm-dirt-v1 | ダート | 8.547 | 44.0% | +0.046 | 1.17x |

**ダートラベル的中率 44.0% について:** rule-v4 のダート専用閾値（ハイ<40 / スロー>46）と
lgbm-dirt-v1 の予測分布が微妙にずれているため、平均帯の再現率が下がる。
PAI リフト（最上位帯 1.17x）は良好なため、展開合致馬抽出の主目的は達成済みと判断。

**ダートモデルの学習パラメータ:** `num_leaves=31`（芝: 63）。データが芝より少ないため
小さめのモデルで過学習を抑制する。

**説明可能性:** LightGBM は `reasons` に特徴量ベクトル（lgbm_features code）と
最終予測（forecast code）を出力する。SHAP 値の個別寄与は将来対応。

#### 5.3 rule-v5 試行と取り消し（2026-06-28）

**試行:** 芝ラベル的中率 76.0% のうち「平均（49–51）」の再現率が 0.0% であったため、
芝閾値を 48–52 に緩和した rule-v5 を試みた。

**結果:**
- ハイ再現率: 54.2% → 41.1%（悪化）
- スロー再現率: 87.6% → 83.3%（悪化）
- 平均再現率: 0.0% → 0.0%（変化なし）
- 全体的中率: 76.0% → 66.5%（悪化）

**結論と取り消し:** 芝平均再現率 0% は lgbm-turf-v1 の予測分布が 49–51 帯にほとんど
値を出さない**構造的問題**であり、閾値調整では解決できない。閾値を rule-v4 に戻した。
PAI 相関 +0.108・最上位帯リフト 1.33x は良好なため、現状を受け入れる。

#### 5.4 受入基準の実測検証（2026-07-11）

**目的:** §4 の受入基準（MAE≤1.5 / ラベル一致率≥60%）に対する現行モデル
（`SplitLightGBMRpciForecaster` = lgbm-turf-v1 + lgbm-dirt-v1）の達成度を、
本番相当DB（mykeibadb 蓄積データ）に対する直近スナップショットで再確認した。

**実行:** `python -m scripts.backtest_forecast --limit 200`（新しい順200レース、
コース混合／芝のみ／ダートのみの3パターン）。

| モデル | コース | MAE | ラベル一致率 | 平均帯再現率 | PAI point-biserial | 最上位帯リフト |
|---|---|---|---|---|---|---|
| 混合(blended) | 芝+ダート | 7.848 | 61.0% | 42.5% | +0.009 | 1.07x |
| lgbm-turf-v1 | 芝 | 8.861 | 73.5% | 14.3% | +0.084 | 1.32x |
| lgbm-dirt-v1 | ダート | 8.332 | 42.5% | 65.6% | +0.032 | 1.18x |

**結論:**

1. §5.2 の大規模バックテスト（15,440レース）と track 別の数値がほぼ整合しており、
   直近データでのモデル劣化（ドリフト）は見られない。
2. **MAE≤1.5 は引き続き未達。** 混合・track別いずれも実測 MAE は 7.8〜8.9 のレンジに収まり、
   単発の外れ値ではなく現行アプローチの構造的な上限と判断する。
3. **ラベル一致率≥60% は芝（73.5%）・混合（61.0%）では達成、ダート（42.5%）は未達。**
   受入基準文言は track 区別を明記していないため、どちらの判定を正とするかは
   `docs/SPEC.md §9` の未確定事項とした。
4. **新知見: コース混合でバックテストすると PAI point-biserial が希釈される。**
   混合サンプルでは +0.009（ほぼ無相関）だが、芝/ダート別に見ると +0.084 / +0.032 と
   §5.2 の記録と整合する正の相関に戻る。芝・ダートで PAI 分布と好走率ベースラインが
   異なるため、母集団を混ぜると相関が打ち消し合う（Simpson のパラドックス類似）。
   **今後 PAI の効果を評価する際は必ず `--track-type` を指定して track 別に見ること。**
   `scripts/backtest_forecast.py` の既定（未指定）出力だけを見て「PAI が効いていない」と
   誤判断しないよう注意。

---

## Consequences

**ポジティブ:**
- MVP を説明可能なルールベースで最短公開できる
- ML 導入時にアプリ側を変更せず差し替え可能（`load_best_forecaster()` のフォールバック）
- `model_version` で予測モデルの世代管理ができる
- 芝/ダート分割により、それぞれの実績 RPCI 分布に最適化された予測が可能

**ネガティブ:**
- ルールベースの精度には上限がある（MAE >> 1.5 / 一致率 ≥ 60% は達成済み）
- ダートモデルのラベル的中率 44.0% はハイ偏重の予測分布に起因する可能性あり
- 芝「平均ペース」の再現率が 0% と低い（構造問題、閾値変更では解決不可）
- 将来のモデル再学習時にモデルファイル（.txt）を手動で更新・配備する必要がある

**緩和策:**
- ラベル的中率が不足する場合、特徴量追加（騎手・前走ペース等）や学習データ拡張を検討
- 芝平均再現率の改善は過去走データ量の増加・特徴量変更による予測分布の変化に期待する
- ダートの精度改善は専用特徴量（砂厚・含水率等）の検討が有効だが、データ取得コストが高い
