# SPEC — 仕様の現状整理

> コード・README・既存資料（docs/design, docs/adr）から確認できる仕様を、確度別に区別する。
> **「実装されている」ことは「正式仕様」ではない。** 迷ったら「未確定事項」に置くこと。

最終更新: 2026-07-11 / 対象コミット `8584e50`

凡例: ✅確定 / 🟡実装済み(仕様書未記載の挙動) / 🧪仮仕様 / ❓未確定 / 🔎要確認

---

## 1. プロダクト前提

- ✅ 対象は **JRA 中央競馬のみ**、日次バッチ更新（速報系は対象外）。（README, design/01）
- ✅ MVP は個人利用・検証用途。生データ非配布、独自指標（PCI/RPCI/PAI/展開コメント）のみ公開。（ADR-0002/README）
- ✅ 認証・課金は MVP 非対応（将来追加可能な構成）。（README）
- ✅ UI に PCI/RPCI 実数値を前面に出さない。言葉/段階評価へ翻訳する。（PROJECT_RULES §5, 旧handoff）

---

## 2. 指標の計算（domain/pace）

- ✅ **PCI**（pci-v2）: `Ave-3F = (走破タイム − 上がり3F) × 600 ÷ (距離 − 600)`、
  `PCI = Ave-3F ÷ 上がり3F × 100 − 50`。均等ペースで 50。式は `pci.py` に隔離。（ADR-0004, pci.py）
- ✅ **RPCI（ラップ由来）**: `RPCI = S3(前半3F)/L3(後半3F) × 100 − 50`。S3/L3 欠損時は全馬 PCI 平均へフォールバック。（pci.py）
- ✅ **PCI3**: 上位3着馬の PCI 平均。（pci.py）
- ✅ **展開3分類**: `classify_pace` が予測・実績で共通。芝は high<49 / slow>51、
  ダートは high<40 / slow>46（rule-v4）。（rpci_forecast.py）
- 🧪 **想定RPCI（rule-v4）**: 距離基準 + コース種別補正（芝+5.0/ダート-9.75）+ 脚質構成 +
  逃げ競合 + 馬場補正 + 前付け馬の近走ペース実績の混合。**重み・閾値は暫定**（`RuleWeights`）。（rpci_forecast.py）
- 🧪 **PAI（pai-v1）**: `100 − RPCI差補正 − 距離補正 − 馬場補正` を base とし、pace_affinity と 50:50 ブレンド。
  閾値・重みは暫定（`PaiWeights`）。（adaptability.py）
- 🧪 **脚質判定**: 過去5走の4角通過順位から 逃/先/差/追/自在。ルールは暫定・最適化余地あり。（running_style.py, design/07）

---

## 3. 展開合致・得意ペース（affinity）

- ✅ **好走の定義**: 3着以内、または重賞での5着以内（`is_good_run`）。学習とバックテストで同一基準。
- 🟡 **好走実績の隣接レベルにじみ**: あるペースレベルの好走実績を、直接隣接するレベルへ
  40%配分してから正規化する（本セッションで追加）。「隣接レベルに直接実績がない=不安(0点)」の
  誤判定を防ぐため。→ 仕様として妥当だが `_NEIGHBOR_BLEED_RATIO=0.4` は 🧪暫定値。（affinity.py）
- 🟡 **展開コメントの分岐**: preferred(ピーク)と今回レベルが異なり、今回レベル自体に高スコアがある場合、
  「Xを中心に、今回のYでも好走実績があり」と表現（本セッションで追加）。（adaptability.py `_blend_pace_affinity`）

---

## 4. 展開コメント（commentary, comment-v1）

- ✅ ルールベース NLG。決定論的・再現可能。生成根拠を `reasons` に出力。（ADR-0008, commentary.py）
- ✅ 初心者向けに実数値・専門用語を出さない（`_PACE_WORD` 等で翻訳）。
- 🟡 **回顧の答え合わせ文言**（本セッションで追加）: 出走前の想定と実績を比較し
  「事前の想定「X」が的中しました」/「事前の想定は「X」でしたが、実際は「Y」…」を付す。
  予測未保存なら従来通り出さない（後方互換）。（commentary.py）
- 🧪 LLM（Gemini）実装は同一 IF で差し替え可能だが、正式運用仕様は未確定。（ADR-0008）

---

## 5. API（presentation）

- ✅ `GET /api/v1/races`（一覧・limit/date）, `/races/dates`, `/races/{key}`,
  `/races/{key}/forecast`, `/races/{key}/pace-analysis`, `/health`。
- ✅ 内部取り込み `POST /internal/ingest/{horses,jockeys,trainers,entries,results,log}`,
  `DELETE /internal/ingest/races/{key}`。`X-Ingest-Token` 認証（未設定時はスキップ=開発モード）。
- 🟡 `pace-analysis` に `forecast_accuracy`（predicted/actual RPCI・label・error・label_hit・model_version）を追加。
  mart に想定RPCI が保存済みのレースのみ非 null（本セッションで追加）。
- ❓ 認証（本番の INGEST_TOKEN 運用）・レート制限・公開 API の範囲は未確定。

---

## 6. 取り込み（ingestion-worker）

- ✅ `--mode fixture|jvlink|mykeibadb`、`--step masters|entries|results|special-entries|all`、`--date/--date-to`、`--chunk-days`。
- ✅ mykeibadb: RA/SE/UM/KS/CH + 特別登録テーブルを読み、Ingest API へ投入。列名は候補リストで吸収。
- 🟡 **上がり3F 妥当範囲チェック**（25.0〜55.0秒）で外れ値レコードを除外（本セッションで追加、
  外部データの異常値が PCI を破壊するのを防ぐ）。範囲値は 🧪暫定。（se_parser.py）
- 🟡 バッチ実行ログを `ingest_log` に記録、失敗時 Webhook 通知（本セッション周辺で追加）。
- ✅ Task Scheduler 自動化: 金・土 10:00 / 日 18:00 に `sync_mykeibadb.bat`。（scripts/, MANUAL_SYNC_GUIDE.md）
- 🔎 JV-Data バイトオフセットは実データ校正済みだが、JV-Link バージョン差で要再確認。（jv_spec.py, se_parser.py）

---

## 7. データモデル（DB）

- ✅ raw / core / mart の3層。core に確定 PCI を埋め込み、mart は version 管理分離（ADR-0006, 0009）。
- ✅ `races.status`（entries/result）+ `race_entries` の NULL 許容で確定前後を同一テーブル管理。
- ✅ mart（predicted_pace / pace_fit）は `model_version` 込みで upsert。
- 🟡 `ingest_log`（batch_date/step/mode/started_at/finished_at/status/error_msg）を追加（migration 002）。

---

## 8. 想定RPCI の受入基準（2026-07-11 実測・検証済み）

**実行環境:** 本番相当 DB（mykeibadb 蓄積データ）。`python -m scripts.backtest_forecast --limit 200`
（新しい順200レース・直近スナップショット）。既存の大規模バックテスト（ADR-0005 §5.2、DB 2022〜2026
約15,440レース）との比較で再現性を確認した。

### 8.1 結果（コース種別を分けない場合）

| 指標 | 値 | 受入基準 | 判定 |
|---|---|---|---|
| MAE | 7.848 | ≤ 1.5 | ❌ 未達（約5倍） |
| RMSE | 10.971 | - | - |
| バイアス | +1.526 | - | - |
| 展開ラベル一致率（blended） | 61.0% | ≥ 60% | ✅ 達成 |
| PAI point-biserial | +0.009 | 正の相関 | 🔎 ほぼ無相関（下記8.3参照） |
| 最上位帯リフト | 1.07x | >1.0x | 🟡 弱い |

### 8.2 結果（コース種別別、model_version 別）

| モデル | コース | MAE | ラベル一致率 | 平均帯再現率 | PAI point-biserial | 最上位帯リフト |
|---|---|---|---|---|---|---|
| lgbm-turf-v1 | 芝 | 8.861 | 73.5% | 14.3% | +0.084 | 1.32x |
| lgbm-dirt-v1 | ダート | 8.332 | 42.5% | 65.6% | +0.032 | 1.18x |

ADR-0005 §5.2 の大規模バックテスト（芝 MAE 9.472/一致率76.0%/相関+0.108/リフト1.33x、
ダート MAE 8.547/一致率44.0%/相関+0.046/リフト1.17x）と**ほぼ整合**。200レースの直近
スナップショットでも数値が大きく崩れていないことを確認した（モデルの経年劣化は今のところ見られない）。

### 8.3 判明した事実・解釈

- ✅ **MAE≤1.5 は未達（構造的）。** 大規模バックテスト・直近200件・芝ダート分割のいずれでも
  MAE は 8.3〜9.5 のレンジで一貫しており、単発の外れ値ではない。現行アプローチ（lgbm-turf/dirt-v1）
  では届かない水準だと判断できる。
- ✅ **展開ラベル一致率 ≥60% は「芝」および「コース混合」では達成、「ダート」は未達（42.5%）。**
  受入基準（design/07, ADR-0005）は芝ダートを区別せず「≥60%」とだけ記載しており、
  判定を track 別に見るか blended で見るかで結論が変わる。→ 未確定事項として 9. に記載。
- 🔎 **コース混合でバックテストすると PAI 相関が希釈される。** 混合サンプルでは
  point-biserial +0.009（ほぼ無相関）だが、芝/ダートに分けると +0.084 / +0.032 と
  歴史的記録と整合する正の相関が見える。芝とダートで PAI のスコア分布・好走率ベースラインが
  異なるため、混合集計は Simpson のパラドックス的に相関を打ち消し合う。
  **→ PAI の効果検証は必ず `--track-type` で分けて評価すること**（`scripts/backtest_forecast.py`
  の既定出力＝混合には現状この落とし穴があり、ツール改善候補として backlog に追記）。
- 🟡 芝「平均(49–51)」再現率は 14.3%（ADR-0005 §5.3 記載の過去値 0% からは改善しているが、
  依然低水準）。rule-v5 試行で「閾値では解決不可の構造問題」と結論済み（ADR-0005 §5.3）。
  今回の再測定でも同じ傾向が続いている。

---

## 9. 未確定事項・今後確認が必要な事項（まとめ）

1. ❓ PAI の正式定義・重み（pai-v1 は暫定）。実運用検証後に確定（C10）。
2. ❓ **想定RPCI 受入基準の達成状況は実測済み（8.節）だが、未達時の方針は未確定。**
   MAE≤1.5 は構造的に未達（現行手法の上限と判断）。ラベル一致率≥60% は「ダート」のみ未達（42.5%）。
   このまま現行モデルで運用を継続するか、追加の要因（特徴量追加・学習データ拡張、ADR-0005 緩和策）に
   投資するかは製品判断が必要（未着手・未指示）。
3. ❓ 受入基準「展開ラベル一致率≥60%」は **芝ダート混合(blended)判定か track別判定か**が
   design/07・ADR-0005 とも明記されておらず未確定。今回の実測では blended=61.0%（達成）・
   芝=73.5%（達成）・ダート=42.5%（未達）と、どちらで見るかで合否が変わる。
4. 🔎 `scripts/backtest_forecast.py` は既定（`--track-type` 未指定）だと芝ダート混合集計になり、
   PAI point-biserial が希釈されて見える（8.3節）。既定出力に track 別内訳を追加するか、
   ドキュメントで常に `--track-type` 併用を促すか要検討（backlog 参照）。
5. ❓ 脚質判定ルールの最適化基準（データ蓄積後・C9）。
6. ❓ 展開コメントの LLM 化を正式採用するか、その品質基準。
7. ❓ 本番の認証（INGEST_TOKEN）・公開範囲・課金の仕様。
8. 🔎 affinity の `_NEIGHBOR_BLEED_RATIO`、上がり3F 妥当範囲などの暫定定数の妥当性検証。
9. 🔎 JV-Data バイトオフセットの JV-Link 新バージョン追従。
10. ❓ 正式公開時の JRA-VAN 規約適合性（法務・C2）。
