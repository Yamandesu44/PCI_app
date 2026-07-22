"""想定RPCI / PAI のバックテスト（予測精度の検証基盤）。

目的: 確定済みレースを「未確定だった時点」に巻き戻して予測を再現し、実績と
比較することで、本プロダクトの中核（展開予想）の精度を数値化する。

測定する2軸:
    1. 想定RPCI の誤差     : predicted_rpci vs rpci_actual（MAE / RMSE / バイアス /
                             展開3分類ラベルの的中率）
    2. PAI のリフト        : PAI 帯ごとの「好走率」。高PAI ほど好走率が高ければ、
                             PAI が展開合致を捉えられている証拠になる。

lookahead 防止が要: 各レースの予測には「そのレース当日より前」の馬履歴だけを
使う。`_AsOfRaceRepository` が find_horse_recent_entries に開催日カットオフを
注入することで、未来のデータ参照（情報漏洩）を防ぐ。

予測経路は本番の ForecastRaceUseCase をそのまま使う（mart 保存なし）。これにより
「出荷されるロジックそのもの」を検証する（評価専用の別経路を作らない）。
"""

from __future__ import annotations

import datetime
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pci.application.dto import ForecastOutput
from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.domain.pace.ability import (
    DEFAULT_WEIGHTS as DEFAULT_ABILITY_WEIGHTS,
)
from pci.domain.pace.ability import (
    AbilityScorer,
    AbilityWeights,
)
from pci.domain.pace.affinity import is_good_run
from pci.domain.pace.commentary import CommentGenerator
from pci.domain.pace.rpci_forecast import PaceLabel, RpciForecaster, classify_pace
from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.race import Race
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.racing.repository import RaceRepository
from pci.domain.shared.race_key import RaceKey

DEFAULT_BAND_EDGES: tuple[int, ...] = (0, 20, 40, 60, 80, 100)


class _AsOfRaceRepository:
    """find_horse_recent_entries に開催日カットオフを差し込む読み取りラッパー。

    ForecastRaceUseCase は履歴取得を 2 引数で呼ぶため、ここで before=as_of を
    強制注入し、予測対象レース当日以降のデータを履歴から除外する。
    その他のメソッドは内側リポジトリへ素通しする。
    """

    def __init__(self, inner: RaceRepository, as_of: datetime.date) -> None:
        self._inner = inner
        self._as_of = as_of

    def find_horse_recent_entries(
        self, ketto_num: str, limit: int = 5, before: datetime.date | None = None
    ) -> list[RaceEntry]:
        # 呼び出し側指定の before があればより厳しい方（早い日付）を採用する。
        cutoff = self._as_of if before is None else min(self._as_of, before)
        return self._inner.find_horse_recent_entries(ketto_num, limit, before=cutoff)

    # ----- 以下は素通し -----
    def find_by_key(self, key: RaceKey) -> Race | None:
        return self._inner.find_by_key(key)

    def find_entries(self, key: RaceKey) -> list[RaceEntry]:
        return self._inner.find_entries(key)

    def list_recent_races(self, limit: int = 50) -> list[Race]:
        return self._inner.list_recent_races(limit)

    def list_race_dates(self) -> list[datetime.date]:
        return self._inner.list_race_dates()

    def list_races_by_date(self, date: datetime.date) -> list[Race]:
        return self._inner.list_races_by_date(date)

    def save_race(self, race: Race) -> None:
        self._inner.save_race(race)

    def save_entry(self, entry: RaceEntry) -> None:
        self._inner.save_entry(entry)

    def delete_entries_not_in(self, key: RaceKey, horse_nos: set[int]) -> int:
        return self._inner.delete_entries_not_in(key, horse_nos)

    def delete_race(self, key: RaceKey) -> bool:
        return self._inner.delete_race(key)

    def find_horse_names(self, ketto_nums: Iterable[str]) -> dict[str, str]:
        return self._inner.find_horse_names(ketto_nums)

    def save_horse(self, horse: Horse) -> None:
        self._inner.save_horse(horse)

    def save_jockey(self, jockey: Jockey) -> None:
        self._inner.save_jockey(jockey)

    def save_trainer(self, trainer: Trainer) -> None:
        self._inner.save_trainer(trainer)

    def ensure_horses(self, ketto_nums: Iterable[str]) -> None:
        self._inner.ensure_horses(ketto_nums)

    def ensure_jockeys(self, codes: Iterable[str]) -> None:
        self._inner.ensure_jockeys(codes)

    def ensure_trainers(self, codes: Iterable[str]) -> None:
        self._inner.ensure_trainers(codes)


# ----- 観測サンプル -----


@dataclass(frozen=True)
class RpciSample:
    """1レース分の想定RPCI 予測と実績のペア。"""

    race_key: str
    predicted: float
    actual: float
    predicted_label: PaceLabel
    actual_label: PaceLabel

    @property
    def error(self) -> float:
        return self.predicted - self.actual


@dataclass(frozen=True)
class HorseSample:
    """1頭分の PAI と好走実績のペア。"""

    race_key: str
    horse_no: int
    pai: float
    good_run: bool


@dataclass(frozen=True)
class IntegratedSample:
    """統合順位1頭分と実績の比較サンプル。"""

    race_key: str
    horse_no: int
    rank: int
    finish_pos: int | None
    good_run: bool


# ----- 集計結果 -----


@dataclass(frozen=True)
class RpciAccuracy:
    """想定RPCI の誤差サマリ。"""

    n: int
    mae: float
    rmse: float
    bias: float
    label_accuracy: float
    per_label_accuracy: dict[str, float]


@dataclass(frozen=True)
class PaiBand:
    """PAI 帯ごとの好走率。"""

    lo: int
    hi: int
    n: int
    good_runs: int

    @property
    def good_rate(self) -> float:
        return self.good_runs / self.n if self.n else 0.0


@dataclass(frozen=True)
class PaiLift:
    """PAI のリフト（高PAI ほど好走するか）サマリ。"""

    n: int
    baseline_rate: float
    bands: list[PaiBand]
    point_biserial: float
    top_band_lift: float  # 最上位帯の好走率 / 全体好走率


@dataclass(frozen=True)
class IntegratedAccuracy:
    """統合順位の実績指標。AbilityWeights比較時の共通評価軸として使う。"""

    n_races: int
    n_horses: int
    top1_win_rate: float
    top1_good_rate: float
    top3_good_capture_rate: float


@dataclass(frozen=True)
class AbilityWeightProfile:
    """実DB比較に使う能力重みの候補。本番設定は書き換えない。"""

    name: str
    description: str
    weights: AbilityWeights


DEFAULT_ABILITY_WEIGHT_PROFILES: tuple[AbilityWeightProfile, ...] = (
    AbilityWeightProfile(
        name="current",
        description="現行重み",
        weights=DEFAULT_ABILITY_WEIGHTS,
    ),
    AbilityWeightProfile(
        name="form-only",
        description="近走内容のみ（Phase 1相当）",
        weights=AbilityWeights(weight_form=1.0, weight_prize=0.0, weight_popularity=0.0),
    ),
    AbilityWeightProfile(
        name="form-heavy",
        description="近走内容を重視",
        weights=AbilityWeights(weight_form=0.70, weight_prize=0.20, weight_popularity=0.10),
    ),
    AbilityWeightProfile(
        name="market-aware",
        description="人気の市場支持をやや重視",
        weights=AbilityWeights(weight_form=0.45, weight_prize=0.30, weight_popularity=0.25),
    ),
)


@dataclass(frozen=True)
class AbilityWeightComparison:
    """同一対象レースでの候補重みと現行重みの差。"""

    profile: AbilityWeightProfile
    accuracy: IntegratedAccuracy | None
    delta_top1_win_rate: float | None
    delta_top1_good_rate: float | None
    delta_top3_good_capture_rate: float | None


@dataclass(frozen=True)
class BacktestReport:
    """バックテスト全体の結果。"""

    model_version: str
    n_races: int
    n_horses: int
    skipped: int
    rpci: RpciAccuracy | None
    pai: PaiLift | None
    integrated: IntegratedAccuracy | None = None
    rpci_samples: list[RpciSample] = field(default_factory=list)
    horse_samples: list[HorseSample] = field(default_factory=list)
    integrated_samples: list[IntegratedSample] = field(default_factory=list)


def summarize_rpci(samples: list[RpciSample]) -> RpciAccuracy | None:
    """想定RPCI 予測の誤差指標を計算する（純粋関数）。"""
    if not samples:
        return None
    n = len(samples)
    errors = [s.error for s in samples]
    mae = sum(abs(e) for e in errors) / n
    rmse = math.sqrt(sum(e * e for e in errors) / n)
    bias = sum(errors) / n
    hits = sum(1 for s in samples if s.predicted_label == s.actual_label)

    per_label: dict[str, float] = {}
    for label in PaceLabel:
        group = [s for s in samples if s.actual_label == label]
        if group:
            correct = sum(1 for s in group if s.predicted_label == label)
            per_label[str(label)] = correct / len(group)
    return RpciAccuracy(
        n=n,
        mae=round(mae, 3),
        rmse=round(rmse, 3),
        bias=round(bias, 3),
        label_accuracy=round(hits / n, 4),
        per_label_accuracy={k: round(v, 4) for k, v in per_label.items()},
    )


def summarize_pai_lift(
    samples: list[HorseSample], band_edges: tuple[int, ...] = DEFAULT_BAND_EDGES
) -> PaiLift | None:
    """PAI 帯ごとの好走率と、PAI と好走の相関（point-biserial）を計算する。"""
    if not samples:
        return None
    n = len(samples)
    total_good = sum(1 for s in samples if s.good_run)
    baseline = total_good / n

    bands: list[PaiBand] = []
    for i in range(len(band_edges) - 1):
        lo, hi = band_edges[i], band_edges[i + 1]
        is_last = i == len(band_edges) - 2
        # 最終帯は上端を含める（PAI=100 を取りこぼさない）。
        members = [s for s in samples if lo <= s.pai < hi or (is_last and s.pai == hi)]
        good = sum(1 for s in members if s.good_run)
        bands.append(PaiBand(lo=lo, hi=hi, n=len(members), good_runs=good))

    top_lift = bands[-1].good_rate / baseline if baseline > 0 and bands else 0.0
    return PaiLift(
        n=n,
        baseline_rate=round(baseline, 4),
        bands=bands,
        point_biserial=round(_point_biserial(samples), 4),
        top_band_lift=round(top_lift, 3),
    )


def summarize_integrated_accuracy(
    samples: list[IntegratedSample],
) -> IntegratedAccuracy | None:
    """統合順位の上位が勝利・好走を捉えた割合を集計する。"""
    if not samples:
        return None
    top1 = [sample for sample in samples if sample.rank == 1]
    good_runs = [sample for sample in samples if sample.good_run]
    return IntegratedAccuracy(
        n_races=len(top1),
        n_horses=len(samples),
        top1_win_rate=round(
            sum(1 for sample in top1 if sample.finish_pos == 1) / len(top1), 4
        )
        if top1
        else 0.0,
        top1_good_rate=round(sum(1 for sample in top1 if sample.good_run) / len(top1), 4)
        if top1
        else 0.0,
        top3_good_capture_rate=round(
            sum(1 for sample in good_runs if sample.rank <= 3) / len(good_runs), 4
        )
        if good_runs
        else 0.0,
    )


def compare_ability_weight_reports(
    reports: dict[str, BacktestReport],
    profiles: tuple[AbilityWeightProfile, ...] = DEFAULT_ABILITY_WEIGHT_PROFILES,
    *,
    baseline_name: str = "current",
) -> list[AbilityWeightComparison]:
    """同一対象で実行した重み別レポートを現行重みと比較する。"""
    baseline_report = reports.get(baseline_name)
    if baseline_report is None:
        raise ValueError(f"基準プロファイルがありません: {baseline_name}")
    baseline = baseline_report.integrated
    comparisons: list[AbilityWeightComparison] = []
    for profile in profiles:
        report = reports.get(profile.name)
        if report is None:
            raise ValueError(f"比較レポートがありません: {profile.name}")
        accuracy = report.integrated
        if (
            baseline is not None
            and accuracy is not None
            and (accuracy.n_races, accuracy.n_horses)
            != (baseline.n_races, baseline.n_horses)
        ):
            raise ValueError(
                f"比較サンプル数が現行重みと一致しません: {profile.name}"
            )
        if baseline is None or accuracy is None:
            deltas: tuple[float | None, float | None, float | None] = (None, None, None)
        else:
            deltas = (
                round(accuracy.top1_win_rate - baseline.top1_win_rate, 4),
                round(accuracy.top1_good_rate - baseline.top1_good_rate, 4),
                round(
                    accuracy.top3_good_capture_rate - baseline.top3_good_capture_rate,
                    4,
                ),
            )
        comparisons.append(
            AbilityWeightComparison(
                profile=profile,
                accuracy=accuracy,
                delta_top1_win_rate=deltas[0],
                delta_top1_good_rate=deltas[1],
                delta_top3_good_capture_rate=deltas[2],
            )
        )
    return comparisons


def group_races_by_track(races: Iterable[Race]) -> dict[str, list[Race]]:
    """レース群をコース種別ごとにグルーピングする。

    コース混合のまま `ForecastBacktester.run()` すると PAI の point-biserial 相関が
    希釈されて見える（芝とダートでスコア分布・好走率ベースラインが異なるため。
    docs/adr/0005-rpci-forecast-strategy.md §5.4）。呼び出し側で track 別にも
    run() を回せるよう、レースを分割するだけの純粋関数として提供する。
    """
    grouped: dict[str, list[Race]] = {}
    for race in races:
        grouped.setdefault(race.track_type, []).append(race)
    return grouped


def report_to_dict(report: BacktestReport) -> dict[str, Any]:
    """BacktestReport をJSON保存用の辞書に変換する（的中率推移の記録・後日の再集計に使う）。"""
    return {
        "model_version": report.model_version,
        "n_races": report.n_races,
        "n_horses": report.n_horses,
        "skipped": report.skipped,
        "rpci": _rpci_accuracy_to_dict(report.rpci),
        "pai": _pai_lift_to_dict(report.pai),
        "integrated": _integrated_accuracy_to_dict(report.integrated),
        "rpci_samples": [_rpci_sample_to_dict(s) for s in report.rpci_samples],
        "horse_samples": [_horse_sample_to_dict(s) for s in report.horse_samples],
        "integrated_samples": [
            _integrated_sample_to_dict(s) for s in report.integrated_samples
        ],
    }


def _rpci_accuracy_to_dict(accuracy: RpciAccuracy | None) -> dict[str, Any] | None:
    if accuracy is None:
        return None
    return {
        "n": accuracy.n,
        "mae": accuracy.mae,
        "rmse": accuracy.rmse,
        "bias": accuracy.bias,
        "label_accuracy": accuracy.label_accuracy,
        "per_label_accuracy": dict(accuracy.per_label_accuracy),
    }


def _pai_lift_to_dict(lift: PaiLift | None) -> dict[str, Any] | None:
    if lift is None:
        return None
    return {
        "n": lift.n,
        "baseline_rate": lift.baseline_rate,
        "point_biserial": lift.point_biserial,
        "top_band_lift": lift.top_band_lift,
        "bands": [
            {"lo": b.lo, "hi": b.hi, "n": b.n, "good_runs": b.good_runs, "good_rate": b.good_rate}
            for b in lift.bands
        ],
    }


def ability_weight_comparisons_to_dict(
    comparisons: list[AbilityWeightComparison],
) -> list[dict[str, Any]]:
    """重み比較結果をJSON保存用の辞書へ変換する。"""
    return [
        {
            "name": item.profile.name,
            "description": item.profile.description,
            "weights": {
                "form": item.profile.weights.weight_form,
                "prize": item.profile.weights.weight_prize,
                "popularity": item.profile.weights.weight_popularity,
            },
            "integrated": _integrated_accuracy_to_dict(item.accuracy),
            "delta_vs_current": {
                "top1_win_rate": item.delta_top1_win_rate,
                "top1_good_rate": item.delta_top1_good_rate,
                "top3_good_capture_rate": item.delta_top3_good_capture_rate,
            },
        }
        for item in comparisons
    ]


def _integrated_accuracy_to_dict(
    accuracy: IntegratedAccuracy | None,
) -> dict[str, Any] | None:
    if accuracy is None:
        return None
    return {
        "n_races": accuracy.n_races,
        "n_horses": accuracy.n_horses,
        "top1_win_rate": accuracy.top1_win_rate,
        "top1_good_rate": accuracy.top1_good_rate,
        "top3_good_capture_rate": accuracy.top3_good_capture_rate,
    }


def _rpci_sample_to_dict(sample: RpciSample) -> dict[str, Any]:
    return {
        "race_key": sample.race_key,
        "predicted": sample.predicted,
        "actual": sample.actual,
        "error": sample.error,
        "predicted_label": str(sample.predicted_label),
        "actual_label": str(sample.actual_label),
    }


def _horse_sample_to_dict(sample: HorseSample) -> dict[str, Any]:
    return {
        "race_key": sample.race_key,
        "horse_no": sample.horse_no,
        "pai": sample.pai,
        "good_run": sample.good_run,
    }


def _integrated_sample_to_dict(sample: IntegratedSample) -> dict[str, Any]:
    return {
        "race_key": sample.race_key,
        "horse_no": sample.horse_no,
        "rank": sample.rank,
        "finish_pos": sample.finish_pos,
        "good_run": sample.good_run,
    }


def format_report(report: BacktestReport) -> str:
    """バックテスト結果を人間可読のテキストへ整形する（CLI 出力用）。"""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"バックテスト結果  model_version={report.model_version or '(不明)'}")
    lines.append(
        f"対象レース {report.n_races} / 出走 {report.n_horses} 頭 "
        f"（スキップ {report.skipped}）"
    )
    lines.append("=" * 60)

    if report.rpci is not None:
        r = report.rpci
        lines.append("\n■ 想定RPCI の誤差")
        lines.append(f"  MAE  : {r.mae:.3f}   RMSE: {r.rmse:.3f}   バイアス: {r.bias:+.3f}")
        lines.append(f"  展開ラベル的中率: {r.label_accuracy:.1%}")
        for label, acc in r.per_label_accuracy.items():
            lines.append(f"    - 実績「{label}」の再現率: {acc:.1%}")
    else:
        lines.append("\n■ 想定RPCI: 有効サンプルなし")

    if report.pai is not None:
        p = report.pai
        lines.append("\n■ PAI のリフト（高PAI ほど好走するか）")
        lines.append(f"  全体好走率(ベースライン): {p.baseline_rate:.1%}")
        lines.append(f"  PAI×好走 の相関(point-biserial): {p.point_biserial:+.3f}")
        lines.append(f"  最上位帯リフト: {p.top_band_lift:.2f}x")
        lines.append("  PAI帯       頭数    好走   好走率   対ベース")
        for b in p.bands:
            lift = (b.good_rate / p.baseline_rate) if p.baseline_rate > 0 else 0.0
            lines.append(
                f"   {b.lo:3d}-{b.hi:<3d}  {b.n:6d}  {b.good_runs:6d}   "
                f"{b.good_rate:5.1%}   {lift:5.2f}x"
            )
    else:
        lines.append("\n■ PAI: 有効サンプルなし")

    if report.integrated is not None:
        i = report.integrated
        lines.append("\n■ 統合順位予想の実績")
        lines.append(f"  1位馬の勝率: {i.top1_win_rate:.1%}")
        lines.append(f"  1位馬の好走率: {i.top1_good_rate:.1%}")
        lines.append(f"  TOP3の好走馬捕捉率: {i.top3_good_capture_rate:.1%}")
    else:
        lines.append("\n■ 統合順位予想: 有効サンプルなし")

    return "\n".join(lines)


def format_ability_weight_comparison(comparisons: list[AbilityWeightComparison]) -> str:
    """重み候補の比較をCLI向けの表に整形する。"""
    lines = [
        "=" * 88,
        "能力重みの同一期間比較（候補は自動採用しません）",
        "候補              form 賞金 人気   1位勝率(差)   1位好走率(差)   TOP3捕捉率(差)",
        "-" * 88,
    ]
    for item in comparisons:
        weights = item.profile.weights
        if item.accuracy is None:
            metrics = "有効サンプルなし"
        else:
            accuracy = item.accuracy
            metrics = (
                f"{accuracy.top1_win_rate:6.1%}({_format_delta(item.delta_top1_win_rate)})  "
                f"{accuracy.top1_good_rate:6.1%}({_format_delta(item.delta_top1_good_rate)})  "
                f"{accuracy.top3_good_capture_rate:6.1%}"
                f"({_format_delta(item.delta_top3_good_capture_rate)})"
            )
        lines.append(
            f"{item.profile.name:<18} "
            f"{weights.weight_form:4.2f} {weights.weight_prize:4.2f} "
            f"{weights.weight_popularity:4.2f}   {metrics}"
        )
    lines.append("=" * 88)
    return "\n".join(lines)


def _format_delta(value: float | None) -> str:
    return "   n/a" if value is None else f"{value:+6.1%}"


def _point_biserial(samples: list[HorseSample]) -> float:
    """PAI（連続）と好走（0/1）の相関係数。分散ゼロや少数時は 0 を返す。"""
    n = len(samples)
    if n < 2:
        return 0.0
    xs = [s.pai for s in samples]
    ys = [1.0 if s.good_run else 0.0 for s in samples]
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mx) ** 2 for x in xs)
    var_y = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    return cov / denom if denom > 0 else 0.0


class ForecastBacktester:
    """確定レース群に対して予測を再現し、実績と突き合わせる。"""

    def __init__(
        self,
        repo: RaceRepository,
        forecaster: RpciForecaster | None = None,
        comment_generator: CommentGenerator | None = None,
        ability_scorer: AbilityScorer | None = None,
        band_edges: tuple[int, ...] = DEFAULT_BAND_EDGES,
    ) -> None:
        self._repo = repo
        self._forecaster = forecaster
        self._commenter = comment_generator
        self._ability_scorer = ability_scorer
        self._band_edges = band_edges

    def run(self, targets: Iterable[Race]) -> BacktestReport:
        rpci_samples: list[RpciSample] = []
        horse_samples: list[HorseSample] = []
        integrated_samples: list[IntegratedSample] = []
        n_races = 0
        skipped = 0
        model_versions: set[str] = set()

        for race in targets:
            if race.rpci_actual is None:
                skipped += 1
                continue
            key = str(race.race_key)
            try:
                out = self._predict_as_of(race)
            except Exception:
                # 履歴皆無・出走馬未登録などはバックテスト対象外として飛ばす。
                skipped += 1
                continue

            model_versions.add(out.model_version)
            rpci_samples.append(
                RpciSample(
                    race_key=key,
                    predicted=out.predicted_rpci,
                    actual=race.rpci_actual,
                    predicted_label=classify_pace(out.predicted_rpci, race.track_type),
                    actual_label=classify_pace(race.rpci_actual, race.track_type),
                )
            )

            actual_entries = self._repo.find_entries(race.race_key)
            finish_by_no = {e.horse_no: e.finish_pos for e in actual_entries}
            for horse in out.horses:
                finish = finish_by_no.get(horse.horse_no)
                horse_samples.append(
                    HorseSample(
                        race_key=key,
                        horse_no=horse.horse_no,
                        pai=horse.pai,
                        good_run=is_good_run(finish, race.grade),
                    )
                )
            if out.integrated_ranking is not None:
                for entry in out.integrated_ranking.entries:
                    finish = finish_by_no.get(entry.horse_no)
                    integrated_samples.append(
                        IntegratedSample(
                            race_key=key,
                            horse_no=entry.horse_no,
                            rank=entry.rank,
                            finish_pos=finish,
                            good_run=is_good_run(finish, race.grade),
                        )
                    )
            n_races += 1

        model_version = " / ".join(sorted(model_versions)) if model_versions else ""
        return BacktestReport(
            model_version=model_version,
            n_races=n_races,
            n_horses=len(horse_samples),
            skipped=skipped,
            rpci=summarize_rpci(rpci_samples),
            pai=summarize_pai_lift(horse_samples, self._band_edges),
            integrated=summarize_integrated_accuracy(integrated_samples),
            rpci_samples=rpci_samples,
            horse_samples=horse_samples,
            integrated_samples=integrated_samples,
        )

    def _predict_as_of(self, race: Race) -> ForecastOutput:
        # mart_repo=None で保存を抑止し、実績データを汚さずに予測だけ再現する。
        as_of_repo = _AsOfRaceRepository(self._repo, race.race_date)
        use_case = ForecastRaceUseCase(
            as_of_repo,
            forecaster=self._forecaster,
            mart_repo=None,
            comment_generator=self._commenter,
            ability_scorer=self._ability_scorer,
        )
        return use_case.execute(str(race.race_key))
