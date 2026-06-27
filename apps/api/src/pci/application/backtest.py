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

from pci.application.dto import ForecastOutput
from pci.application.forecast_use_cases import ForecastRaceUseCase
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
class BacktestReport:
    """バックテスト全体の結果。"""

    model_version: str
    n_races: int
    n_horses: int
    skipped: int
    rpci: RpciAccuracy | None
    pai: PaiLift | None
    rpci_samples: list[RpciSample] = field(default_factory=list)
    horse_samples: list[HorseSample] = field(default_factory=list)


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

    return "\n".join(lines)


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
        band_edges: tuple[int, ...] = DEFAULT_BAND_EDGES,
    ) -> None:
        self._repo = repo
        self._forecaster = forecaster
        self._commenter = comment_generator
        self._band_edges = band_edges

    def run(self, targets: Iterable[Race]) -> BacktestReport:
        rpci_samples: list[RpciSample] = []
        horse_samples: list[HorseSample] = []
        n_races = 0
        skipped = 0
        model_version = ""

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

            model_version = model_version or out.model_version
            rpci_samples.append(
                RpciSample(
                    race_key=key,
                    predicted=out.predicted_rpci,
                    actual=race.rpci_actual,
                    predicted_label=classify_pace(out.predicted_rpci),
                    actual_label=classify_pace(race.rpci_actual),
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
            n_races += 1

        return BacktestReport(
            model_version=model_version,
            n_races=n_races,
            n_horses=len(horse_samples),
            skipped=skipped,
            rpci=summarize_rpci(rpci_samples),
            pai=summarize_pai_lift(horse_samples, self._band_edges),
            rpci_samples=rpci_samples,
            horse_samples=horse_samples,
        )

    def _predict_as_of(self, race: Race) -> ForecastOutput:
        # mart_repo=None で保存を抑止し、実績データを汚さずに予測だけ再現する。
        as_of_repo = _AsOfRaceRepository(self._repo, race.race_date)
        use_case = ForecastRaceUseCase(
            as_of_repo,
            forecaster=self._forecaster,
            mart_repo=None,
            comment_generator=self._commenter,
        )
        return use_case.execute(str(race.race_key))
