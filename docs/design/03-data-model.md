# 設計書 03: データモデル設計

DB は **raw / core / mart の3層**（ADR-0006）。PostgreSQL。

---

## 1. raw 層（原本・改変禁止）

### raw_jvdata
JV-Link 固定長レコードを原文保存。監査・再パースの源泉。

| 列 | 型 | 説明 |
|---|---|---|
| id | bigserial PK | |
| data_spec | text | JV-Data種別（蓄積系等） |
| record_type | char(2) | RA / SE / UM / KS / CH |
| record_key | text | レコード内キー（重複検知用） |
| payload | text | 固定長レコード原文 |
| ingested_at | timestamptz | 取り込み日時 |
| source_batch | text | 取り込みバッチID |

- 追記のみ。`(record_type, record_key)` で冪等性を担保。

---

## 2. core 層（正規化ドメイン）

### races（開催年でレンジパーティション）
| 列 | 型 | 説明 |
|---|---|---|
| race_key | char(16) PK | 年+月日+競馬場+回+日目+R |
| race_date | date | 開催日 |
| jyo_cd | char(2) | 競馬場コード |
| distance | int | 距離(m) |
| track_type | text | 芝 / ダート / 障害 |
| track_condition | text | 良/稍重/重/不良 |
| weather | text | 天候 |
| grade | text | グレード（G1等） |
| race_class | text | クラス・条件 |
| field_size | int | 出走頭数 |
| status | text | 確定前(entries) / 確定後(result) |
| rpci_actual | numeric | 実績RPCI（確定後） |
| pci3_actual | numeric | PCI3（確定後） |

### race_lap_times
| 列 | 型 | 説明 |
|---|---|---|
| race_key | char(16) FK | |
| furlong_no | int | ハロン番号 |
| lap_time | numeric | 当該ハロンタイム(秒) |
| PK | (race_key, furlong_no) | |

### horses
| 列 | 型 | 説明 |
|---|---|---|
| ketto_num | char(10) PK | 血統登録番号 |
| name | text | 馬名 |
| sex | text | 性別 |
| birth_year | int | 生年 |

### jockeys / trainers
| 列 | 型 |
|---|---|
| code | text PK |
| name | text |

### race_entries（開催年でレンジパーティション）
出馬表（確定前）と成績（確定後）を `status` で状態管理。

| 列 | 型 | 説明 |
|---|---|---|
| race_key | char(16) FK | |
| horse_no | int | 馬番 |
| frame_no | int | 枠番 |
| ketto_num | char(10) FK | |
| weight | numeric | 馬体重（kg。既存カラム名との互換性のため名称を維持） |
| jockey_code | text FK | |
| trainer_code | text FK | |
| finish_pos | int NULL | 着順（確定後） |
| race_time | numeric NULL | 走破タイム（確定後） |
| agari_3f | numeric NULL | 上がり3F（確定後） |
| corner_1..4 | int NULL | 各コーナー通過順位（確定後） |
| pci_actual | numeric NULL | PCI（確定後・pci.py算出） |
| running_style | text NULL | 脚質 |
| PK | (race_key, horse_no) | |

---

## 3. mart 層（分析結果・再計算可能）

すべて `formula_version` または `model_version` 必須。core を入力に再生成可能。

### predicted_pace（想定RPCI）
| 列 | 型 | 説明 |
|---|---|---|
| race_key | char(16) | |
| model_version | text | 例 "rule-v1" |
| predicted_rpci | numeric | 想定RPCI |
| pace_label | text | スロー/平均/ハイ |
| confidence | numeric | 信頼度 |
| reasons | jsonb | 要因内訳（説明可能性） |
| computed_at | timestamptz | |
| PK | (race_key, model_version) | |

### pace_fit（PAI・展開合致馬）
| 列 | 型 | 説明 |
|---|---|---|
| race_key | char(16) | |
| horse_no | int | |
| model_version | text | |
| pai | numeric | 0〜100 |
| fit_label | text | 恩恵/中立/不利 |
| reasons | jsonb | 減点内訳（RPCI差/距離/馬場） |
| PK | (race_key, horse_no, model_version) | |

### pci_recalc（任意・PCI式バージョン管理）
| 列 | 型 | 説明 |
|---|---|---|
| race_key | char(16) | |
| horse_no | int | |
| formula_version | text | 例 "pci-v1" |
| pci | numeric | |
| reasons | jsonb | |
| PK | (race_key, horse_no, formula_version) | |

---

## 4. インデックス・パーティション方針

- `races` / `race_entries`: **開催年でレンジパーティション**（5年→10年へ拡張）
- 分析用インデックス: `races(jyo_cd, distance, track_condition)`、`race_entries(ketto_num, ...)`
- mart: `(race_key, model_version)` で最新版を素早く取得

---

## 5. 設計上の論点（要注意）

| 論点 | 方針 |
|---|---|
| 確定前/確定後の状態管理 | `races.status` / `race_entries` のNULL許容で同一テーブル管理。予測は確定前、答え合わせは確定後 |
| version 必須 | mart層は version 列なしの行を作らない（影響追跡・再計算のため） |
| 生データ非提供（C2） | API は core/mart の生値を直接公開せず、独自指標DTOに変換して返す |
| 競馬場コード保持 | 中央のみ取り込みだが、地方拡張に備え jyo_cd は汎用的に保持 |
