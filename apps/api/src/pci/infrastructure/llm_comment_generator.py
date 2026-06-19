"""Gemini REST API を使った展開コメント生成器（comment-gemini-v1・ADR-0008）。

google-genai パッケージは不要。httpx で Gemini v1beta REST エンドポイントを
直接呼び出すため、C拡張依存ゼロで動作する。
API エラー・パースエラー時はルールベース（comment-v1）にフォールバックし
サービス継続性を確保する。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from pci.domain.pace.commentary import (
    Commentary,
    ForecastCommentInput,
    ReviewCommentInput,
    RuleBasedCommentGenerator,
)
from pci.domain.pace.rpci_forecast import PaceLabel
from pci.domain.shared.reason import Reason

_log = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_COMMENTARY_VERSION = "comment-gemini-v1"

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_PACE_WORD: dict[PaceLabel, str] = {
    PaceLabel.HIGH: "速い流れ（ハイペース）",
    PaceLabel.AVERAGE: "平均的な流れ",
    PaceLabel.SLOW: "緩い流れ（スローペース）",
}


class GeminiCommentGenerator:
    """Gemini REST API で展開コメントを生成する（comment-gemini-v1）。

    ADR-0008: LLM は指標→表現の写像のみを担い、数値・判定はドメインで確定済み。
    GEMINI_API_KEY が未設定の場合、DI がこのクラスを使わず rule-based を返す。
    """

    def __init__(
        self,
        api_key: str,
        model: str = GEMINI_MODEL,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._http = http_client or httpx.Client(timeout=30.0)
        self._fallback = RuleBasedCommentGenerator()

    def forecast_comment(self, data: ForecastCommentInput) -> Commentary:
        try:
            return self._generate_forecast(data)
        except Exception as exc:
            _log.warning("Gemini forecast_comment 失敗 → rule-based: %s", exc)
            return self._fallback.forecast_comment(data)

    def review_comment(self, data: ReviewCommentInput) -> Commentary:
        if data.rpci_actual is None:
            return self._fallback.review_comment(data)
        try:
            return self._generate_review(data)
        except Exception as exc:
            _log.warning("Gemini review_comment 失敗 → rule-based: %s", exc)
            return self._fallback.review_comment(data)

    def _generate_forecast(self, data: ForecastCommentInput) -> Commentary:
        parsed = self._call_api(_build_forecast_prompt(data))
        headline = str(parsed.get("headline", "")).strip()
        body = [str(p).strip() for p in parsed.get("body", []) if str(p).strip()]
        if not headline or not body:
            raise ValueError(f"Gemini レスポンスが不完全です: {parsed}")
        return Commentary(
            headline=headline,
            body=tuple(body),
            model_version=GEMINI_COMMENTARY_VERSION,
            reasons=_forecast_reasons(data),
        )

    def _generate_review(self, data: ReviewCommentInput) -> Commentary:
        parsed = self._call_api(_build_review_prompt(data))
        headline = str(parsed.get("headline", "")).strip()
        body = [str(p).strip() for p in parsed.get("body", []) if str(p).strip()]
        if not headline or not body:
            raise ValueError(f"Gemini レスポンスが不完全です: {parsed}")
        return Commentary(
            headline=headline,
            body=tuple(body),
            model_version=GEMINI_COMMENTARY_VERSION,
            reasons=_review_reasons(data),
        )

    def _call_api(self, prompt: str) -> dict[str, Any]:
        url = _GEMINI_URL.format(model=self._model)
        resp = self._http.post(
            url,
            params={"key": self._api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"},
            },
        )
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
        text: str = payload["candidates"][0]["content"]["parts"][0]["text"]
        result: dict[str, Any] = json.loads(text)
        return result


# ----- プロンプト構築 -----


def _build_forecast_prompt(data: ForecastCommentInput) -> str:
    beneficiary_text = (
        "・".join(f"{b.horse_no}番（展開向き度 {b.pai}）" for b in data.beneficiaries)
        if data.beneficiaries
        else "特になし"
    )
    confidence_note = (
        "・段落4: 確信度が低いため、逆の展開になる可能性も一言添える"
        if data.confidence < 0.5
        else ""
    )
    return f"""あなたは競馬展開予想の解説者です。
以下の分析データを元に、競馬をあまり知らない人でも理解できるやさしい日本語でコメントを書いてください。

=== 分析データ ===
距離: {data.distance_m}m、馬場: {data.track_type}
出走頭数: {data.field_size}頭
想定されるペース: {_PACE_WORD[data.pace_label]}（想定指数: {data.predicted_rpci}）
展開の確信度: {data.confidence:.0%}
前に行きたい馬の頭数: {len(data.front_runners)}頭
展開が向くと予想される馬（馬番・適性スコア）: {beneficiary_text}

=== 出力ルール ===
・PCI・RPCI・PAI・脚質コードなど専門用語は使わない
・headline: 展開の結論を20〜35文字で一文にまとめる
・body: 以下の段落構成にする
  - 段落1: 前に行く馬が何頭いて、レースの流れがどうなりそうか
  - 段落2: そのペースになると何が起きやすいか（脚質的な有利・不利）
  - 段落3: 展開が向く馬の紹介（いなければ「力どおりに決まりそう」などの旨）
  {confidence_note}

必ず以下のJSONフォーマットのみを返してください（コードブロック不要）:
{{"headline": "...", "body": ["...", "...", "..."]}}"""


def _build_review_prompt(data: ReviewCommentInput) -> str:
    assert data.rpci_actual is not None
    pci3_text = f"{data.pci3_actual}" if data.pci3_actual is not None else "算出不可"
    rpci = data.rpci_actual

    if rpci > 51.0:
        pace_desc = "前半が緩く、前が止まりにくい流れ"
    elif rpci < 49.0:
        pace_desc = "前半から速く、差しが届きやすい流れ"
    else:
        pace_desc = "大きな偏りのない平均的な流れ"

    winner_text = "不明"
    confirmed = [h for h in data.horses if h.finish_pos is not None]
    if confirmed:
        w = min(confirmed, key=lambda h: h.finish_pos if h.finish_pos is not None else 9999)
        style = f"（{w.running_style}）" if w.running_style else ""
        pci_text = f"、自身のペース指数 {w.pci}" if w.pci is not None else ""
        winner_text = f"{w.horse_no}番{style}{pci_text}"

    sample_note = (
        "・段落3: 完走データが少ないため評価は参考値である旨を一言添える"
        if data.sample_size < 3
        else ""
    )
    return f"""あなたは競馬回顧の解説者です。
以下のレース結果データを元に、競馬をあまり知らない人でも理解できるやさしい日本語で振り返りコメントを書いてください。

=== レース結果データ ===
実際のレースのペース: {pace_desc}（ペース指数: {rpci}）
上位3頭の平均ペース: {pci3_text}
集計対象の完走馬数: {data.sample_size}頭
勝ち馬: {winner_text}

=== 出力ルール ===
・PCI・RPCI・PCI3など専門用語は使わず平易な表現にする
・headline: 実際のペースを20〜35文字で一文にまとめる
・body: 以下の段落構成にする
  - 段落1: 実際にどんなペースになり、どんな展開だったか
  - 段落2: 勝ち馬がどういう形で勝ったか
  {sample_note}

必ず以下のJSONフォーマットのみを返してください（コードブロック不要）:
{{"headline": "...", "body": ["...", "..."]}}"""


# ----- reasons 生成 -----


def _forecast_reasons(data: ForecastCommentInput) -> tuple[Reason, ...]:
    return (
        Reason(
            code="comment_basis",
            description=(
                f"想定RPCI {data.predicted_rpci}（{data.pace_label}）・"
                f"展開合致 {len(data.beneficiaries)}頭・確信度 {data.confidence:.0%} を基に生成"
            ),
        ),
        Reason(
            code="comment_model",
            description=f"Gemini API 生成（{GEMINI_COMMENTARY_VERSION}・{GEMINI_MODEL}）",
        ),
    )


def _review_reasons(data: ReviewCommentInput) -> tuple[Reason, ...]:
    rpci = data.rpci_actual if data.rpci_actual is not None else "—"
    pci3 = data.pci3_actual if data.pci3_actual is not None else "—"
    return (
        Reason(
            code="comment_basis",
            description=(
                f"実績RPCI {rpci}・PCI3 {pci3}・対象{data.sample_size}頭"
                f"（{data.formula_version}）を基に生成"
            ),
        ),
        Reason(
            code="comment_model",
            description=f"Gemini API 生成（{GEMINI_COMMENTARY_VERSION}・{GEMINI_MODEL}）",
        ),
    )
