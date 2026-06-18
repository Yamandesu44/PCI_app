"""展開シナリオ生成モジュール。

想定RPCI 予測と各馬の PAI を、競馬ファンが直感的に理解できる
日本語の「展開予想」へ翻訳する。本プロダクトのコアバリュー
「PCI を理解していない競馬ファンでも展開予想を活用できる」を担う層。

純粋なドメインロジック（説明文の組み立てルール）であり、外部依存を持たない。
"""

from __future__ import annotations

from dataclasses import dataclass

from pci.domain.pace.adaptability import FitLabel, HorsePaceProfile, PaiResult
from pci.domain.pace.rpci_forecast import PaceLabel, RpciForecast
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.reason import Reason

_FRONT_STYLES = (RunningStyleLabel.ESCAPE, RunningStyleLabel.FRONT)

_HEADLINE: dict[PaceLabel, str] = {
    PaceLabel.HIGH: "ハイペース濃厚 — 差し・追込の台頭に注目",
    PaceLabel.AVERAGE: "平均ペース — 紛れ少なく実力勝負",
    PaceLabel.SLOW: "スローペース濃厚 — 前残り・先行有利",
}


@dataclass(frozen=True)
class PaceScenario:
    """展開シナリオ（UI 表示用の構造化ナラティブ）。"""

    pace_label: PaceLabel
    headline: str
    detail: str
    front_runners: tuple[int, ...]
    beneficiaries: tuple[int, ...]
    reasons: tuple[Reason, ...]


def build_pace_scenario(
    forecast: RpciForecast,
    fit_results: list[PaiResult],
    profiles: list[HorsePaceProfile],
) -> PaceScenario:
    """想定RPCI と PAI から展開シナリオを生成する。

    Args:
        forecast:    想定RPCI 予測結果
        fit_results: 各馬の PAI 結果
        profiles:    各馬の脚質プロファイル（fit_results と同じ馬を含む）

    Returns:
        PaceScenario（見出し・詳細・先行馬・展開合致馬・reasons）
    """
    front_runners = tuple(p.horse_no for p in profiles if p.running_style in _FRONT_STYLES)

    matched = sorted(
        (r for r in fit_results if r.fit_label == FitLabel.MATCHED),
        key=lambda r: r.pai,
        reverse=True,
    )
    beneficiaries = tuple(r.horse_no for r in matched)

    headline = _HEADLINE[forecast.label]
    detail = _build_detail(forecast, front_runners, matched)

    reasons = (
        Reason(
            code="scenario_pace",
            description=f"想定RPCI {forecast.value}（{forecast.label}）を基準に展開を構成",
        ),
        Reason(
            code="scenario_beneficiaries",
            description=(
                f"展開合致馬 {len(beneficiaries)}頭"
                + (f"（馬番 {list(beneficiaries)}）" if beneficiaries else "（該当なし）")
            ),
        ),
    )

    return PaceScenario(
        pace_label=forecast.label,
        headline=headline,
        detail=detail,
        front_runners=front_runners,
        beneficiaries=beneficiaries,
        reasons=reasons,
    )


def _build_detail(
    forecast: RpciForecast,
    front_runners: tuple[int, ...],
    matched: list[PaiResult],
) -> str:
    front_part = (
        f"先行争いに絡みそうなのは馬番 {list(front_runners)}。"
        if front_runners
        else "明確な先行馬が見当たらず、ペースは落ち着きやすい。"
    )

    if matched:
        top = matched[0]
        bene_part = (
            f"この展開で恩恵を受けやすいのは馬番 {top.horse_no}（PAI {top.pai}）を筆頭とする"
            f"{len(matched)}頭。"
        )
    else:
        bene_part = "突出して展開が向く馬は少なく、力関係どおりに決まりやすい。"

    return f"想定RPCIは{forecast.value}で{forecast.label}ペースの公算。{front_part}{bene_part}"
