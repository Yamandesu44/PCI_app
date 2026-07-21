# JV-Data 仕様追従 手順書

JV-Link（JRA-VAN DataLab）の JV-Data 仕様書が新バージョンになったとき、または
取り込み結果に「仕様が変わったかもしれない」兆候が出たときに、`jv_spec.py` ほか
バイトオフセット定義を安全に確認・更新するための手順書。

対象読者: 開発者本人（yuuta）。実データの取得は JV-Link が使える Windows 実行機
（`C:\Users\yuuta\PCI_app`）でのみ可能（ADR-0002）。クラウド上の Claude Code /
Codex セッションは JV-Link に接続できないため、この手順の 2.1（実データ取得）は
実行できない。2.2 以降のオフライン検証・`jv_spec.py` 更新・テスト更新は
`raw_dump/` の保存済みファイルさえあればどちらの環境でも進められる。

---

## 0. 前提知識（おさらい）

- JV-Data のフィールド位置は仕様書上すべて **バイト** 単位（Shift-JIS/CP932）。
  全角文字は2byte・半角は1byte。JV-Link が返す Unicode 文字列を**文字位置**で
  スライスすると、全角フィールド（レース名・馬名など）を跨いだ時点で以降の
  全フィールドがズレる（`jv_spec.py` モジュール docstring 参照）。
- RA/SE のオフセット定義の**唯一の真実の場所**は `src/ingestion/parser/jv_spec.py`。
  各フィールドは `confidence` を持つ:
  - `CONFIRMED`: 実データで検証済み（実測日・レース・確認方法を `note` に明記）
  - `TENTATIVE`: 未検証・要確認（値は入るが位置がズレている可能性がある）
- UM/KS/CH（マスタ）は `master_parsers.py` に独自のオフセット定義がある。
  こちらは **Ver.3.0.0 → Ver.4.9 の実データ差分を既に確認・反映済み**
  （ketto_num 直後に日付フィールド群24byteが追加され、名前位置が後方にシフトした）。
  この移行作業が、本手順書のもとになった実例。
- **未確認の点**: RA/SE の現在のオフセットが実際にどの JV-Data バージョンの
  出力を元に校正されたのかは確認されていない（`docs/SPEC.md §9-8` 参照）。
  `README.md` と `common.py` docstring は「Ver.3.0.0 準拠」と書いているが、
  実際のオフセット値は 2026-06 の実データ（`dump_records.py`/`verify_layout.py`/
  `locate_haron.py`/`locate_corners.py` で校正、当時 JV-Link 経由で取得）を
  元にしており、UM/KS/CH と同じ Ver.4.9 相当の出力から逆算した可能性がある。
  「Ver.3.0.0 準拠」の記述が更新し忘れの古いラベルなのか、RA/SE は本当に
  Ver.3.0.0 から構造が変わっていないのかは、本手順を一度実施して確認するまで
  独断で判定しない。

## 1. いつ実施するか（トリガー条件）

以下のいずれかに該当したら本手順を実施する。

1. JRA-VAN DataLab から JV-Data 仕様書の新バージョンリリース案内があった。
2. 取り込みバッチ（`batch.py --mode jvlink` / `--mode mykeibadb`）で特定
   フィールドの値が急に異常・空白になった、パースエラーが増えた等、
   仕様変更を疑う兆候が出た。
3. JV-Link または mykeibadb 側のソフトウェアバージョンを更新した直後。
4. 新しいレコード種別（例: 現在未対応の HR/O1 等）を追加で取り込みたい。

## 2. 手順

### 2.1 実データを保存する（Windows 実行機・JV-Link 必須）

```powershell
cd C:\Users\yuuta\PCI_app\apps\ingestion-worker
py -3.12-32 src\ingestion\dump_records.py
```

`raw_dump/`（`.gitignore` 済み・生データはコミット禁止）に最新の RA/SE 等が
保存される。以降は JV-Link を叩かずオフラインで繰り返し検証できる。

### 2.2 アンカーで大枠のズレを検知する

```powershell
py -3.12-32 -m ingestion.parser.verify_layout raw_dump\dumped_ra.txt
py -3.12-32 -m ingestion.parser.verify_layout raw_dump\dumped_se.txt
```

`[アンカー検証]`（RecordSpec / DataKubun / MakeDate / 開催年月日）が全て OK
なら、レコード先頭の共通ヘッダ領域は無事＝致命的な全面ズレはない。ここが
NG ならレコード長・エンコード前提から疑う（CR/LF 処理・`encode("cp932")`
忘れ等、仕様変更以前の実装ミスの可能性が高い）。

### 2.3 CONFIRMED フィールドの値が意味的に正しいか目視確認する

アンカーが OK でも、個別フィールドがズレている可能性はある。`verify_layout`
の出力で `✓`（CONFIRMED）フィールドの値を、実際のレース結果（JRA 公式・
netkeiba 等）と突き合わせる。特に Kyori/TrackCD/HaronTimeL3（RPCI 算出に
直結）とコーナー通過順位（脚質判定に直結）を優先的に確認する。

### 2.4 ズレを発見したら新しい位置を特定する

汎用: `--map` オプションで非空白領域マップ + バイトルーラーを出力し、
目視で探す。

```powershell
py -3.12-32 -m ingestion.parser.verify_layout --map raw_dump\dumped_ra.txt
```

既知フィールド向けの専用ツールもある（同じ手法の実装例。新フィールドを
特定するツールが要る場合はこれらを雛形にする）:

```powershell
# RA: HaronTimeL3（レース後半3F、RPCI算出用）
py -3.12-32 -m ingestion.locate_haron raw_dump\dumped_ra.txt "12.0 10.7 11.2 11.3 11.4 11.9"

# SE: コーナー通過順位1〜4
py -3.12-32 -m ingestion.locate_corners raw_dump\dumped_se_result.txt 4 4 5 4
```

いずれも「JRA 結果ページの実際の値」を引数に渡し、その値が並ぶバイト位置を
逆算する仕組み。**複数レース（芝・ダート、頭数の異なるレース）で一致する
ことを確認してから CONFIRMED に昇格させる**（1レースだけの一致は偶然の
可能性がある。`locate_corners.py` は複数ファイル交差検証モードに対応）。

### 2.5 `jv_spec.py` を更新する

- `offset`/`length` を新しい値に更新する。
- `confidence` は実データ複数件で確認できたら `CONFIRMED`、1件のみ・
  未確認なら `TENTATIVE` のままにする。
- `note` に **実測日・レース（開催場・R番号・距離）・確認方法** を記載する
  （既存フィールドの記法に合わせる。例:「実測確定: 2026-06-13 函館1R」）。
- `RA_RECORD_BYTES`/`SE_RECORD_BYTES`（レコード総長）が変わっていないかも
  `verify_layout` の「レコード長」アンカーで確認する。

### 2.6 パーサ・テストを更新する

- `ra_parser.py`/`se_parser.py` が対応フィールドを読んでいれば、その読み出し
  ロジックも合わせて確認する（`jv_spec.py` 更新だけでは反映されない箇所が
  ないか）。
- `tests/test_verify_layout.py`・`tests/test_locate_haron.py`・
  `tests/test_locate_corners.py` など既存テストの fixture・期待値を更新する。
- `fixtures/`（開発用サンプルレコード）も新レイアウトに合わせて更新するか
  検討する。
- API 側に影響するなら（PCI/RPCI の計算式自体は不変でも、入力データの意味が
  変わるなら）ゴールデンテスト
  （`apps/api/tests/unit/domain/pace/test_pci_golden.py`）が引き続きパスする
  か確認する。

### 2.7 記録する

- コミットメッセージに変更根拠（旧オフセット → 新オフセット、確認した
  レース、仕様書上どのバージョンの変更か）を残す（`PROJECT_RULES.md §6`
  準拠）。
- `docs/SPEC.md §9`（未確定事項）・`docs/HANDOFF.md` を更新する。
- バージョン追従が完了したら、`README.md` の「Ver.X.X 準拠」表記と
  `common.py` の docstring も、実際に確認したバージョンへ更新する
  （現状は 0 節の通り未確認のまま放置されている）。

## 3. 安全策・注意点

- **一度に全フィールドを疑わない**。まずアンカー（共通ヘッダ領域、`[0:33]`
  付近の半角コード領域）で全面ズレの有無を判定してから、個別 TENTATIVE
  フィールドに進む。アンカー自体は仕様変更でもほぼ動かない前提
  （レコード種別ID・DataKubun・作成日は JV-Data 仕様の骨格部分）。
- **生レコードは `raw_dump/` 限定・コミット禁止**（JRA-VAN 生データ再配布
  禁止、`.gitignore` 済み）。ログ添付・スクリーンショット等でも生データの
  内容を外部に貼らない。
- **1レースの一致だけで CONFIRMED に昇格しない**。特にコーナー通過順位や
  HaronTime のように、他の数値と偶然一致する候補が出ることがあるフィールド
  は、芝・ダート/頭数の異なる複数レースで交差検証する。
- **既存の CONFIRMED フィールドが今回の確認で値が変わっていたら要注意**。
  「仕様変更」なのか「取得したレコードの種類が違う」（DataKubun 違い等）
  なのかを切り分けてから対応する。

## 4. 関連ファイル一覧

```
apps/ingestion-worker/src/ingestion/
├── parser/
│   ├── jv_spec.py           # RA/SEバイトオフセット定義（唯一の真実の場所）
│   ├── verify_layout.py     # 仕様マップ照合ハーネス（アンカー検証+フィールド一覧+バイトマップ）
│   ├── common.py            # 共通ユーティリティ（バイト抽出・CP932変換）
│   ├── ra_parser.py         # RAパーサ（jv_spec参照）
│   ├── se_parser.py         # SEパーサ（jv_spec参照）
│   └── master_parsers.py    # UM/KS/CHパーサ（独自オフセット定義、Ver.4.9実測済み）
├── dump_records.py          # JV-Linkから実レコードを取得しraw_dump/へ保存
├── locate_haron.py          # RA: HaronTimeL3位置特定ツール
└── locate_corners.py        # SE: コーナー通過順位位置特定ツール
```

## 5. 更新履歴

| 日付 | 内容 |
|---|---|
| 2026-07-13 | 初版作成（`tasks/backlog.md` C節）。UM/KS/CH の Ver.3.0.0 → Ver.4.9 移行実績を参考に、RA/SE 側の追従手順として明文化。 |
