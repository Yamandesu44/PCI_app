# 公開しているデータの棚卸し

- 状態: 調査結果（2026-08-06 時点）
- 目的: JRA-VAN 規約確認の判断材料

## なぜ要るのか

CLAUDE.md の方針は「**公開するのは独自指標・分析結果のみ**、生データの再配布は禁止前提」。

公開した以上、**実際に何が読み出せるのか**を方針と突き合わせておく必要がある。
規約確認は法務の判断だが、**判断材料としての「実際の公開範囲」は技術側でしか出せない**。

対象は `/api/v1/*`（`PUBLIC_API_TOKEN` で保護・web からサーバ間で呼ぶ）と、
そこから web が画面に出すもの。`/internal/ingest/*` は別トークンで、取り込み専用。

## 区分

返している項目を3つに分ける。

### A. 独自指標・分析結果（方針上、公開してよいもの）

| 項目 | 中身 |
|---|---|
| `pai` / `fit_label` / `low_evidence` | 展開適性（pai-v4） |
| `pci` / `pci_actual` / `rpci_actual` / `pci3_actual` | 自前の計算式（pci-v3） |
| `predicted_rpci` / `pace_label` / `confidence` | 想定ペース（LightGBM） |
| `running_style` | 過去5走の通過順位から自前で判定した脚質 |
| `style_advantage` | 脚質別の展開有利度（style-advantage-v4） |
| `integrated_ranking` | 展開×能力の統合順位（integrated-v1） |
| `scenario_headline` / `comment` | 展開の自然文解説 |
| `reasons` | 各算出の根拠 |

これらは JRA-VAN のデータを**入力に使って自分で計算した結果**であり、元データではない。

### B. 公表事実（JRA が一般に公表しているもの）

| 項目 | 備考 |
|---|---|
| `race_date` / `jyo_cd` / `distance_m` / `track_type` | レースの基本情報 |
| `grade` / `race_class` / `field_size` | 同上 |
| `track_condition` / `weather` | 馬場状態・天候 |
| `horse_name` / `horse_no` / `frame_no` | 出走馬・馬番・枠番 |
| `finish_pos` | 着順 |
| `agari_3f_s` | 上がり3F |

**ここが規約確認の焦点。** 内容自体は JRA が公表している事実だが、こちらは
JRA-VAN の配信データを経由して取得している。「公表事実だから自由」と言えるのか、
「配信データ由来である以上は再配布に当たる」と見るのかは、**規約の解釈であって
技術で決められない**。件数を挙げておくと、確定済み15,931レース・219,329出走分。

### C. 元データ側の識別子（公開しない）

| 項目 | 扱い |
|---|---|
| `ketto_num`（血統登録番号） | **公開APIから削除した**（下記） |
| `jockey_code` / `trainer_code` | 公開APIでは返していない（取り込み側のみ） |

## 今回直したこと

**`ketto_num` を公開レスポンスから外した。** JRA-VAN 側のマスターキーそのもので、
出しておくと**手元のデータを元データへ突き合わせやすくする**。web は一切使っておらず、
置いておく利点が無かった。取り込み側（`/internal/ingest/*`）では引き続き使う。

## 承知の上で残していること

**指数の実数値は画面のHTMLに含まれる。** モバイル表示はクライアントコンポーネントで、
サーバから渡した `analysis` がそのままページのペイロードへ載る。画面には言葉
（「速い流れ」等）しか出ないが、ソースを見れば数値がある。

これは区分Aであり方針違反ではない。UI の規則（実数値を出さない）は**表示の話**で、
非専門家に数字を突きつけない、が目的。その目的は満たしている。

## 判断が要ること

- [ ] **区分Bの扱い。** 公表事実の再掲を JRA-VAN の規約がどう扱うか。
      技術側では決められないので、規約本文の確認が要る。
- [ ] **取得経路が2段であること。** 現在の運用は `--mode mykeibadb` で、
      JV-Link から直接ではない（JRA-VAN → mykeibadb → 本アプリ）。
      確認すべき規約が2つある可能性がある。

## 閉じ方（規約確認が済むまで）

**入口は2つある。web だけ閉じても API から同じデータが取れる。** 片方だけ塞いで
「閉じた」と思うのが一番危ない。

### 1. web（訪問者向け）

Vercel の Settings → Environments → **Production** に2つ追加して再デプロイ。

```
BETA_ACCESS_USER      = <任意>
BETA_ACCESS_PASSWORD  = <任意>
```

`apps/web/src/middleware.ts` が Basic 認証を要求する。実装の性質:

- 両方とも未設定 → 素通し（ローカル開発のため）
- **片方だけ設定 → 503 で閉じる**。設定ミスで開いたままにしない
- 照合は定数時間比較。資格情報はログにも画面にも出さない
- `matcher` は `_next/static` / `_next/image` / `favicon.ico` だけ除外。
  ページも API ルートも通る（現状 route handler は無い）

### 2. API（Cloud Run・外から直接届く）

`--allow-unauthenticated` で公開されており、**`PUBLIC_API_TOKEN` を知っていれば
誰でも同じ JSON を取得できる**。レート制限は120回/分だが、時間をかけた
まとめ取りは防げない。

**このトークンは構築中の会話ログに平文で残っている。** web を閉じても、
トークンを持つ側から見れば何も変わらない。**必ず入れ替えること。**

```bash
gcloud run services update pci-api --region asia-northeast1 \
  --update-env-vars PUBLIC_API_TOKEN=<新しい値>
```

同じ値を3か所へ揃える（ズレると画面が401になる）:

| 場所 | 変数名 |
|---|---|
| Cloud Run | `PUBLIC_API_TOKEN` |
| Vercel（Production） | `API_ACCESS_TOKEN` |
| GitHub Secrets（監視用） | `PUBLIC_API_TOKEN` |

ワーカーが使う `INGEST_TOKEN` は別系統なので影響しない。

### 確認

```bash
cd apps/api
python scripts/check_deployment.py --base-url <公開URL>            # 401 になること
python scripts/check_deployment.py --base-url <公開URL> --token <新>  # 6項目 ✓
```

web は素の `curl` で 401、ブラウザで認証ダイアログが出れば閉じている。
