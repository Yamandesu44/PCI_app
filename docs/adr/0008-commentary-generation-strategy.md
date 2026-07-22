# ADR-0008: 展開コメント生成戦略 — MVPルールベースNLG + LLM疎結合IF

- **Status:** Accepted
- **Date:** 2026-06-19
- **Deciders:** @yamandesu44

---

## Context

本プロダクトのコアバリューは「PCI を理解していない競馬ファンでも展開予想を活用できる」こと。
想定RPCI・PAI・PCI といった独自指標は強力だが、数値のままでは非専門家に伝わらない。
そこで、指標を**自然文の「解説（展開コメント）」へ翻訳する出力**を最終段に置く。

要件:
- MVP では**説明可能性・再現性を最優先**する（どの指標から何を述べたかを追跡可能に）
- 将来的に LLM で表現力・自然さを高める余地を残す
- 生データ・認証情報を出力に含めない（法務・セキュリティ前提）
- 出力は「独自指標・分析結果（PAI、展開予想、AIコメント等）」の範囲に限定する

---

## Decision

### 1. 戦略インターフェース（疎結合・ADR-0005 と同方針）

コメント生成ロジックを差し替え可能にするため、domain 層に戦略インターフェースを定義する。

```
apps/api/src/pci/domain/pace/commentary.py

CommentGenerator (Protocol)
  forecast_comment(ForecastCommentInput) -> Commentary   # 出走前（展開予想）
  review_comment(ReviewCommentInput)     -> Commentary   # 確定後（ペース回顧）
      Commentary = { headline, body, model_version, reasons }

実装:
  RuleBasedCommentGenerator   # MVP（comment-v1・テンプレートNLG）
  LlmCommentGenerator         # 将来（comment-llm-v*）※同一IFを満たす・infrastructure 層
```

application / presentation 層は `CommentGenerator` にのみ依存し、具体実装は DI で注入する。
**LLM への差し替えがアプリ側コード変更ゼロで可能**。入力 VO（ForecastCommentInput /
ReviewCommentInput）は指標スカラに正規化済みで、LLM プロンプト構築にもそのまま使える。

**2026-07-22追記:** 出走前入力に`horse_numbers_confirmed`を追加した。枠順未確定時の暫定連番を
公式馬番として文章化しないための表示状態で、数値・判定ロジック自体は変更しない。対応版は
ルールベース`comment-v2`、Gemini`comment-gemini-v2`とする。v1の記載は初期設計の履歴として残す。

**2026-07-22追記（モデル移行）:** `gemini-2.0-flash`の提供終了に対応し、Gemini実装の既定を
`gemini-3.5-flash`へ移行した。`GEMINI_MODEL`でモデルを上書き可能にし、生成根拠には実際に
使用したモデル名を残す。対応版は`comment-gemini-v3`とする。APIキー未設定・呼出失敗時の
`comment-v2`フォールバック、および数値・判定をドメインで確定する原則は変更しない。

**2026-07-22追記（ゼロコスト既定）:** `COMMENT_GENERATOR_MODE`を追加し、既定を`rule`とした。
環境にAPIキーが残っていても既定では外部通信しない。Geminiは`gemini`モードとAPIキーを
両方明示した場合だけ有効化する。これにより無料枠の変更と無関係に通常運用の外部API費用を
ゼロへ固定する。

### 2. MVP: ルールベース NLG（`model_version = "comment-v1"`）

説明可能性と再現性を最優先し、指標を決定論的にテンプレート文へ写像する:

| 入力 | 文章化のルール |
|---|---|
| 展開ラベル（ハイ/平均/スロー） | 結論見出し＋「なぜそうなると何が起きるか」の一文を選択 |
| 先行志向の頭数 | 「前に行きたい馬が N 頭」の句を生成 |
| 想定RPCI / 実績RPCI | ペースの言い換え（速い/緩い流れ）に変換 |
| 展開合致馬（PAI上位） | 「恩恵を受けやすいのは◯番（PAI xx）」 |
| 確信度 | 0.5 未満なら逆目を促す注意書きを付加 |
| 勝ち馬の PCI と実績RPCI の差（回顧） | 「後半に脚を伸ばす / 前々で押し切る / 流れに対応」を選択 |

LLM を使わないため**出力が完全に再現可能**で、生成根拠（どの指標から何を述べたか）を
`reasons` に明示できる。専門用語は色・バー・自然文へ翻訳する Web 層（pace.ts）と役割分担する。

### 3. 説明可能性

- すべての Commentary に `reasons`（`comment_basis` / `comment_model`）を付す
- `model_version`（comment-v1）を出力し、UI の「コメントの根拠」に表示する
- これにより「AI が言っているから」ではなく「指標がこう出ているから」を担保する

### 4. 将来: LLM（`model_version = "comment-llm-v*"`）

- 同一インターフェース `CommentGenerator` を infrastructure 層で実装
- 入力は本 ADR の入力 VO を JSON 化してプロンプトに与える（指標→文章の写像のみを依頼）
- **数値・判定はドメインで確定**させ、LLM には表現だけを任せる（指標の捏造を防ぐ）
- ルールベースは**フォールバック / ベースライン**として常設する
- API キー等は `.env` で管理し、生データ・認証情報を出力・コミットに含めない

---

## Consequences

**ポジティブ:**
- MVP を説明可能・再現可能なルールベースで最短公開できる
- LLM 導入時にアプリ側を変更せず差し替え可能
- `model_version` でコメント生成方式の世代管理ができる
- 数値はドメインで確定するため、LLM 化しても指標の整合性が崩れない

**ネガティブ:**
- テンプレート NLG は表現の多様性に乏しく、文章が機械的になりやすい

**緩和策:**
- ラベル・頭数・確信度による分岐でバリエーションを確保
- 表現力が要件化したら LLM 実装（comment-llm-v*）へ移行（IF は不変）
