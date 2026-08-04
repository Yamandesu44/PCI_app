"""GeminiCommentGenerator のユニットテスト（httpx.Client をモック注入）。"""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import Mock

import httpx

from pci.domain.pace.commentary import (
    BeneficiaryRef,
    ForecastCommentInput,
    ReviewCommentInput,
    ReviewHorseRef,
)
from pci.domain.pace.rpci_forecast import PaceLabel
from pci.infrastructure.llm_comment_generator import (
    GEMINI_COMMENTARY_VERSION,
    GEMINI_MODEL,
    GeminiCommentGenerator,
)

# ----- テスト用ヘルパー -----

_BEGINNER_FORBIDDEN = re.compile(r"\b(PCI3?|RPCI|PAI)\b|\d+\.\d+", re.IGNORECASE)


def _visible_text(result) -> str:
    body = "\n".join(result.body)
    return f"{result.headline}\n{body}"


def _make_http_client(headline: str, body: list[str]) -> Mock:
    """正常レスポンスを返すモック httpx.Client を生成する。"""
    text = json.dumps({"headline": headline, "body": body})
    resp = Mock(spec=httpx.Response)
    resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    resp.raise_for_status.return_value = None
    client = Mock(spec=httpx.Client)
    client.post.return_value = resp
    return client


def _make_error_client(exc: Exception) -> Mock:
    """post() が例外を送出するモック httpx.Client を生成する。"""
    client = Mock(spec=httpx.Client)
    client.post.side_effect = exc
    return client


def _forecast_input(
    pace_label: PaceLabel = PaceLabel.HIGH,
    confidence: float = 0.7,
    front_runners: tuple[int, ...] = (1, 3),
    beneficiaries: tuple[BeneficiaryRef, ...] = (BeneficiaryRef(4, 84.5),),
    horse_numbers_confirmed: bool = True,
) -> ForecastCommentInput:
    return ForecastCommentInput(
        distance_m=1800,
        track_type="芝",
        field_size=10,
        pace_label=pace_label,
        predicted_rpci=48.1,
        confidence=confidence,
        front_runners=front_runners,
        beneficiaries=beneficiaries,
        horse_numbers_confirmed=horse_numbers_confirmed,
    )


def _review_input(
    rpci_actual: float | None = 53.0,
    sample_size: int = 8,
) -> ReviewCommentInput:
    return ReviewCommentInput(
        rpci_actual=rpci_actual,
        pci3_actual=52.5,
        formula_version="pci-v3",
        track_type="芝",
        field_size=10,
        sample_size=sample_size,
        horses=(
            ReviewHorseRef(horse_no=1, finish_pos=1, running_style="逃", pci=54.2),
            ReviewHorseRef(horse_no=5, finish_pos=2, running_style="先", pci=51.8),
        ),
    )


# ----- 展開予想コメントのテスト -----


class TestForecastComment:
    def test_returns_gemini_headline(self) -> None:
        client = _make_http_client("差し・追い込みが狙い目の展開です。", ["本文1", "本文2"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.forecast_comment(_forecast_input())
        assert result.headline == "差し・追い込みが狙い目の展開です。"

    def test_returns_gemini_body(self) -> None:
        body = ["段落1", "段落2", "段落3"]
        client = _make_http_client("見出し", body)
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.forecast_comment(_forecast_input())
        assert list(result.body) == body

    def test_sanitizes_raw_indexes_from_visible_text(self) -> None:
        client = _make_http_client(
            "想定RPCIは48.1です。",
            ["PAI 84.5の馬が向きます。", "PCI3は52.5です。"],
        )
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.forecast_comment(_forecast_input())
        assert _BEGINNER_FORBIDDEN.search(_visible_text(result)) is None

    def test_model_version_is_gemini(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.forecast_comment(_forecast_input())
        assert result.model_version == GEMINI_COMMENTARY_VERSION

    def test_reasons_include_comment_model(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.forecast_comment(_forecast_input())
        codes = [r.code for r in result.reasons]
        assert "comment_model" in codes
        assert "comment_basis" in codes

    def test_reasons_model_description_mentions_gemini(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.forecast_comment(_forecast_input())
        model_reason = next(r for r in result.reasons if r.code == "comment_model")
        assert "Gemini" in model_reason.description
        assert GEMINI_MODEL == "gemini-3.5-flash"
        assert GEMINI_MODEL in model_reason.description

    def test_falls_back_to_rule_based_on_http_error(self) -> None:
        client = _make_error_client(httpx.NetworkError("接続失敗"))
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.forecast_comment(_forecast_input())
        # フォールバック時は rule-based の model_version になる
        assert result.model_version != GEMINI_COMMENTARY_VERSION
        assert result.headline  # フォールバック結果は空ではない

    def test_falls_back_on_malformed_response(self) -> None:
        bad_text = '{"no_headline": true}'
        resp = Mock(spec=httpx.Response)
        resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": bad_text}]}}]}
        resp.raise_for_status.return_value = None
        client = Mock(spec=httpx.Client)
        client.post.return_value = resp
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.forecast_comment(_forecast_input())
        assert result.model_version != GEMINI_COMMENTARY_VERSION

    def test_api_key_sent_in_request(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("my_secret_key", http_client=client)
        gen.forecast_comment(_forecast_input())
        call_kwargs = client.post.call_args
        assert call_kwargs.kwargs["params"]["key"] == "my_secret_key"

    def test_json_mime_type_in_request(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        gen.forecast_comment(_forecast_input())
        body: dict[str, Any] = client.post.call_args.kwargs["json"]
        assert body["generationConfig"]["response_mime_type"] == "application/json"

    def test_model_override_used_in_url(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", model="gemini-2.5-flash", http_client=client)
        gen.forecast_comment(_forecast_input())
        url: str = client.post.call_args.args[0]
        assert "gemini-2.5-flash" in url

    def test_model_override_is_recorded_in_reason(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", model="gemini-2.5-flash-lite", http_client=client)

        result = gen.forecast_comment(_forecast_input())

        model_reason = next(r for r in result.reasons if r.code == "comment_model")
        assert "gemini-2.5-flash-lite" in model_reason.description

    def test_low_confidence_prompts_caveat_in_call(self) -> None:
        """確信度 < 0.5 のとき、プロンプトに逆展開の注意書き指示が含まれる。"""
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        gen.forecast_comment(_forecast_input(confidence=0.3))
        prompt: str = client.post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        assert "逆" in prompt

    def test_unconfirmed_horse_number_is_registration_order_in_prompt(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        gen.forecast_comment(_forecast_input(horse_numbers_confirmed=False))

        prompt: str = client.post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        assert "登録順 4（馬番未確定）" in prompt
        assert "4番" not in prompt


# ----- 回顧コメントのテスト -----


class TestReviewComment:
    def test_returns_gemini_headline(self) -> None:
        client = _make_http_client("スローペースで前が粘った展開でした。", ["本文1", "本文2"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.review_comment(_review_input())
        assert result.headline == "スローペースで前が粘った展開でした。"

    def test_model_version_is_gemini(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.review_comment(_review_input())
        assert result.model_version == GEMINI_COMMENTARY_VERSION

    def test_sanitizes_review_raw_indexes_from_visible_text(self) -> None:
        client = _make_http_client(
            "実績RPCIは53.0でした。",
            ["PCI3は52.5で、勝ち馬のPCIは54.2です。"],
        )
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.review_comment(_review_input())
        assert _BEGINNER_FORBIDDEN.search(_visible_text(result)) is None

    def test_falls_back_when_rpci_is_none(self) -> None:
        """rpci_actual が None の場合は API を呼ばずにフォールバックする。"""
        client = Mock(spec=httpx.Client)
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.review_comment(_review_input(rpci_actual=None))
        client.post.assert_not_called()
        # rule-based のフォールバックが返る
        assert result.model_version != GEMINI_COMMENTARY_VERSION

    def test_falls_back_on_api_error(self) -> None:
        client = _make_error_client(httpx.TimeoutException("タイムアウト"))
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.review_comment(_review_input())
        assert result.model_version != GEMINI_COMMENTARY_VERSION
        assert result.headline

    def test_reasons_include_basis_and_model(self) -> None:
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        result = gen.review_comment(_review_input())
        codes = {r.code for r in result.reasons}
        assert codes == {"comment_basis", "comment_model"}

    def test_small_sample_noted_in_prompt(self) -> None:
        """sample_size < 3 のときプロンプトにデータ不足の注意指示が含まれる。"""
        client = _make_http_client("見出し", ["本文"])
        gen = GeminiCommentGenerator("fake", http_client=client)
        gen.review_comment(_review_input(sample_size=2))
        prompt: str = client.post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        assert "参考値" in prompt
