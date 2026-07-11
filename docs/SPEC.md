# SPEC — 仕様の現状整理

> コード・README・既存資料（docs/design, docs/adr）から確認できる仕様を、確度別に区別する。
> **「実装されている」ことは「正式仕様」ではない。** 迷ったら「未確定事項」に置くこと。

最終更新: 2026-07-11 / 対象コミット `9712fd2`

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

## 8. 想定RPCI の受入基準（design で言及・未達成の可能性）

- ❓ 受入基準として MAE ≤ 1.5 / 展開ラベル一致率 ≥ 60% が design/07 に記載。
  現状 rule-v4 がこれを満たすかは 🔎バックテストで要検証（`scripts/backtest_forecast.py` は集計を print のみ、永続化なし）。
- ❓ 芝「平均(49–51)」再現率が 0% という既知の構造的課題（rpci_forecast.py の docstring）。
  PAI 相関は良好なため主目的は達成という判断が置かれているが、正式な合否は未確定。

---

## 9. 未確定事項・今後確認が必要な事項（まとめ）

1. ❓ PAI の正式定義・重み（pai-v1 は暫定）。実運用検証後に確定（C10）。
2. ❓ 想定RPCI 受入基準の達成状況と、未達時の要因追加方針。
3. ❓ 脚質判定ルールの最適化基準（データ蓄積後・C9）。
4. ❓ 展開コメントの LLM 化を正式採用するか、その品質基準。
5. ❓ 本番の認証（INGEST_TOKEN）・公開範囲・課金の仕様。
6. 🔎 affinity の `_NEIGHBOR_BLEED_RATIO`、上がり3F 妥当範囲などの暫定定数の妥当性検証。
7. 🔎 JV-Data バイトオフセットの JV-Link 新バージョン追従。
8. ❓ 正式公開時の JRA-VAN 規約適合性（法務・C2）。
