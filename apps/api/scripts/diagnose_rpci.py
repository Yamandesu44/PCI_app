"""rpci_actual / pci_actual のデータ品質診断スクリプト。

バックテストで MAE が 47〜116 という異常値が出た原因を特定するため、
DB に格納された値の分布と外れ値を表示する。

使い方:
    cd apps/api
    python -m scripts.diagnose_rpci
    python -m scripts.diagnose_rpci --show-outliers   # 外れ値の詳細表示
    python -m scripts.diagnose_rpci --by-track-year   # コース種別×年の分布と中立点の妥当性
    python -m scripts.diagnose_rpci --compare-rpci-formula  # 現行式とTARGET一致式の乖離実測
"""

from __future__ import annotations

import argparse
import sys
from typing import NamedTuple

sys.path.insert(0, "src")

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from pci.config.settings import get_settings
from pci.domain.pace.pci import calculate_rpci_from_lap, calculate_rpci_target
from pci.domain.pace.rpci_forecast import classify_pace
from pci.domain.pace.style_advantage import neutral_rpci
from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime
from pci.infrastructure.database.models import RaceEntryModel, RaceModel
from pci.infrastructure.database.session import build_engine, build_session_maker


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="rpci_actual / pci_actual 品質診断")
    p.add_argument("--show-outliers", action="store_true", help="外れ値レースを一覧表示")
    p.add_argument(
        "--compare-rpci-formula",
        action="store_true",
        help="現行のRPCI式とTARGET一致式の乖離を実測する（本番設定は変えない）",
    )
    p.add_argument("--rpci-min", type=float, default=20.0, help="正常範囲の下限 (default: 20)")
    p.add_argument("--rpci-max", type=float, default=90.0, help="正常範囲の上限 (default: 90)")
    p.add_argument(
        "--by-track-year",
        action="store_true",
        help="コース種別×年で分布と中立点(style-advantage-v4)の妥当性を診断する",
    )
    # 最新年は年途中までしかないため、通年の他年と並べると季節差が年差に化ける。
    # 月で窓を揃えて初めて年同士を対等に比較できる。
    p.add_argument(
        "--month-from",
        type=int,
        default=1,
        choices=range(1, 13),
        metavar="1-12",
        help="--by-track-year で集計する月の下限（年をまたいで窓を揃える。default: 1）",
    )
    p.add_argument(
        "--month-to",
        type=int,
        default=12,
        choices=range(1, 13),
        metavar="1-12",
        help="--by-track-year で集計する月の上限（default: 12）",
    )
    args = p.parse_args()
    if args.month_from > args.month_to:
        p.error("--month-from は --month-to 以下にしてください")
    return args


def _month_window_note(month_from: int, month_to: int) -> str:
    if month_from == 1 and month_to == 12:
        return "通年"
    return f"{month_from}〜{month_to}月のみ"


def _print_track_year_distribution(
    session: Session, lo: float, hi: float, month_from: int, month_to: int
) -> None:
    """コース種別×年で rpci_actual の分布と中立点の位置を表示する。

    脚質別有利度は「中立点からどちら側へ何ポイント離れたか」だけで前・後どちらを
    有利とするかを決める（style_advantage.neutral_rpci）。中立点は閾値から導く固定値なので、
    実績分布が年をまたいでずれると、同じルールでも有利／不利の振り分け比率が変わり、
    ラベルの意味が薄まる。ここではその「ずれ」を直接観測する。
    """
    print("\n" + "=" * 78)
    print(
        "■ コース種別 × 年の rpci_actual 分布と中立点の妥当性"
        f"（{_month_window_note(month_from, month_to)}）"
    )
    print("=" * 78)
    for track_type in ("芝", "ダート"):
        neutral = neutral_rpci(track_type)
        print(f"\n  ── {track_type}（現行の中立点 {neutral:.1f}）")
        header = (
            f"  {'年':>6s} {'件数':>7s} {'平均':>7s} {'中央':>7s} "
            f"{'中立との差':>11s} {'スロー側%':>10s}"
        )
        print(header)
        rows = session.execute(
            text(
                """
                SELECT
                    EXTRACT(YEAR FROM race_date)::int                       AS yr,
                    COUNT(*)                                                AS cnt,
                    AVG(rpci_actual)                                        AS avg_v,
                    percentile_cont(0.50) WITHIN GROUP (ORDER BY rpci_actual) AS p50,
                    SUM(CASE WHEN rpci_actual > :neutral THEN 1 ELSE 0 END) AS slow_side
                FROM races
                WHERE status = 'result'
                  AND rpci_actual IS NOT NULL
                  AND rpci_actual >= :lo
                  AND rpci_actual <= :hi
                  AND track_type = :track_type
                  AND EXTRACT(MONTH FROM race_date) BETWEEN :month_from AND :month_to
                GROUP BY yr
                ORDER BY yr
                """
            ),
            {
                "neutral": neutral,
                "lo": lo,
                "hi": hi,
                "track_type": track_type,
                "month_from": month_from,
                "month_to": month_to,
            },
        ).all()
        for yr, cnt, avg_v, p50, slow_side in rows:
            slow_pct = slow_side / cnt * 100 if cnt else 0.0
            print(
                f"  {yr:6d} {cnt:7,d} {avg_v:7.1f} {p50:7.1f} "
                f"{avg_v - neutral:+11.1f} {slow_pct:9.1f}%"
            )
    print(
        "\n  読み方: 「中立との差」が年ごとに動く、または「スロー側%」が50%から大きく"
        "\n  外れて年ごとに変わる場合、固定の中立点が実績分布とずれている。"
    )
    _print_track_year_style_mix(session, month_from, month_to)


def _print_track_year_style_mix(session: Session, month_from: int, month_to: int) -> None:
    """コース種別×年で確定脚質(race_entries.running_style)の構成比を表示する。

    有利度の検証は確定脚質を入力に使うため、実績分布のずれ（上の表）だけでなく、
    脚質ラベルそのものの分布や欠損率が年で変われば同じルールの見え方が変わる。
    2つを並べて初めて「馬場・レース傾向の変化」と「データ側の変化」を区別できる。
    自在は有利度スコアの対象外（_SCOREABLE_STYLES）なので、独立した列として出す。
    """
    print("\n" + "=" * 78)
    print(
        "■ コース種別 × 年の確定脚質の構成比"
        f"（有利度の入力データ側の変化を見る・{_month_window_note(month_from, month_to)}）"
    )
    print("=" * 78)
    for track_type in ("芝", "ダート"):
        print(f"\n  ── {track_type}")
        print(
            f"  {'年':>6s} {'対象頭数':>9s} {'逃げ%':>7s} {'先行%':>7s} "
            f"{'差し%':>7s} {'追込%':>7s} {'自在%':>7s} {'未設定%':>8s}"
        )
        rows = session.execute(
            text(
                """
                SELECT
                    EXTRACT(YEAR FROM r.race_date)::int AS yr,
                    COUNT(*)                            AS cnt,
                    SUM(CASE WHEN e.running_style = '逃げ' THEN 1 ELSE 0 END) AS escape,
                    SUM(CASE WHEN e.running_style = '先行' THEN 1 ELSE 0 END) AS front,
                    SUM(CASE WHEN e.running_style = '差し' THEN 1 ELSE 0 END) AS stalker,
                    SUM(CASE WHEN e.running_style = '追込' THEN 1 ELSE 0 END) AS closer,
                    SUM(CASE WHEN e.running_style = '自在' THEN 1 ELSE 0 END) AS flexible,
                    SUM(CASE WHEN e.running_style IS NULL THEN 1 ELSE 0 END)  AS unset
                FROM race_entries e
                JOIN races r ON r.race_key = e.race_key
                WHERE r.status = 'result'
                  AND r.track_type = :track_type
                  AND EXTRACT(MONTH FROM r.race_date) BETWEEN :month_from AND :month_to
                GROUP BY yr
                ORDER BY yr
                """
            ),
            {
                "track_type": track_type,
                "month_from": month_from,
                "month_to": month_to,
            },
        ).all()
        for yr, cnt, escape, front, stalker, closer, flexible, unset in rows:
            shares = [v / cnt * 100 if cnt else 0.0 for v in (escape, front, stalker, closer)]
            flexible_pct = flexible / cnt * 100 if cnt else 0.0
            unset_pct = unset / cnt * 100 if cnt else 0.0
            body = " ".join(f"{share:6.1f}%" for share in shares)
            print(f"  {yr:6d} {cnt:9,d} {body} {flexible_pct:6.1f}% {unset_pct:7.1f}%")
    print(
        "\n  読み方: 構成比や未設定%が特定の年だけ大きく動いていれば、レース傾向ではなく"
        "\n  取り込み・脚質判定側の変化を疑う。"
    )
    _print_track_year_rpci_source(session, month_from, month_to)


def _print_track_year_rpci_source(session: Session, month_from: int, month_to: int) -> None:
    """コース種別×年で rpci_actual の算出経路の内訳を表示する。

    `aggregate_rpci` は race_s3f/race_l3f があればレースラップ由来（TARGET準拠）を使い、
    無ければ全完走馬PCIの平均というフォールバックへ縮退する。この2経路は同じ
    「RPCI」でも値の出方が違うため、ラップ保有率が年で変われば分布そのものが動く。
    分布のずれを「競馬側の変化」と読む前に、まずここを潰す。
    """
    print("\n" + "=" * 78)
    print(
        "■ コース種別 × 年の rpci_actual 算出経路"
        f"（ラップ由来 vs 全馬PCI平均フォールバック・{_month_window_note(month_from, month_to)}）"
    )
    print("=" * 78)
    for track_type in ("芝", "ダート"):
        print(f"\n  ── {track_type}")
        print(
            f"  {'年':>6s} {'件数':>7s} {'ラップ有%':>10s} "
            f"{'ラップ由来の平均':>17s} {'代替の平均':>12s}"
        )
        rows = session.execute(
            text(
                """
                SELECT
                    EXTRACT(YEAR FROM race_date)::int AS yr,
                    COUNT(*)                          AS cnt,
                    SUM(CASE WHEN race_s3f IS NOT NULL AND race_l3f IS NOT NULL
                        THEN 1 ELSE 0 END)            AS with_lap,
                    AVG(CASE WHEN race_s3f IS NOT NULL AND race_l3f IS NOT NULL
                        THEN rpci_actual END)         AS avg_lap,
                    AVG(CASE WHEN race_s3f IS NULL OR race_l3f IS NULL
                        THEN rpci_actual END)         AS avg_fallback
                FROM races
                WHERE status = 'result'
                  AND rpci_actual IS NOT NULL
                  AND track_type = :track_type
                  AND EXTRACT(MONTH FROM race_date) BETWEEN :month_from AND :month_to
                GROUP BY yr
                ORDER BY yr
                """
            ),
            {
                "track_type": track_type,
                "month_from": month_from,
                "month_to": month_to,
            },
        ).all()
        for yr, cnt, with_lap, avg_lap, avg_fallback in rows:
            lap_pct = with_lap / cnt * 100 if cnt else 0.0
            lap_txt = f"{avg_lap:17.1f}" if avg_lap is not None else f"{'-':>17s}"
            fb_txt = f"{avg_fallback:12.1f}" if avg_fallback is not None else f"{'-':>12s}"
            print(f"  {yr:6d} {cnt:7,d} {lap_pct:9.1f}% {lap_txt} {fb_txt}")
    print(
        "\n  読み方: 「ラップ有%」が年で大きく動き、かつ2経路の平均が離れている場合、"
        "\n  分布のずれの主因は競馬側ではなくラップ取り込みの欠落・変化である。"
    )


def _first_segment_m(distance_m: int) -> int:
    """ハロンタイムの先頭区間の距離(m)。200mで割り切れない距離だけ端数になる。"""
    return distance_m % 200 or 200


class _LapRow(NamedTuple):
    """RPCI式の比較に必要な、1レース分の実測値。"""

    race_key: str
    race_date: str
    track_type: str
    distance_m: int
    s3f: float
    l3f: float
    winner_time: float

    @property
    def s3_distance_m(self) -> int:
        """前半3F が実際にカバーする距離(m)。

        JRAのハロンタイムは、距離が200mで割り切れない場合だけ先頭区間が端数になる
        （1300m = 100m + 200m×6）。したがって先頭3区間の合計は常に600mではなく、
        端数のある距離では500mになる。L3側は端数が先頭にあるため常に600m。
        """
        return _first_segment_m(self.distance_m) + 400

    @property
    def implied_mid_pace(self) -> float | None:
        """S3・L3・走破タイムから逆算した中間区間の平均ペース(秒/F)。

        3者が同じレースの値なら 中間時間 = 走破タイム − S3 − L3 で、
        その区間距離は 距離 − S3の距離 − 600m。中間区間が無い距離は検査できない（None）。
        """
        mid_distance = self.distance_m - self.s3_distance_m - 600
        if mid_distance <= 0:
            return None
        return (self.winner_time - self.s3f - self.l3f) / (mid_distance / 200.0)


class _FormulaSample(NamedTuple):
    """1レースにおける新旧RPCI式の比較結果。"""

    row: _LapRow
    current: float
    target: float
    current_label: str
    target_label: str

    @property
    def diff(self) -> float:
        return self.target - self.current

    @property
    def label_changed(self) -> bool:
        return self.current_label != self.target_label


# JRAの200m平均は概ね11〜14秒。両端(S3/L3)が11〜12秒/Fのレースで中間だけ15秒/F超は
# 競走として起こらないため、そのようなレースは3者が同一レースの値ではないと判断する。
_PLAUSIBLE_MID_LO = 9.0
_PLAUSIBLE_MID_HI = 15.0


def _percentile(sorted_values: list[float], q: float) -> float:
    return sorted_values[min(len(sorted_values) - 1, int(len(sorted_values) * q))]


def _fetch_lap_rows(session: Session) -> list[_LapRow]:
    """レースラップと勝ち馬タイムが揃う確定レースを取得する。

    レース走破タイムは勝ち馬のタイムを使う（TARGET のレースPCI と同じ定義）。
    """
    rows = session.execute(
        text(
            """
            SELECT r.race_key, r.race_date, r.track_type, r.distance_m,
                   r.race_s3f, r.race_l3f, w.race_time_s
            FROM races r
            JOIN (
                SELECT DISTINCT ON (race_key) race_key, race_time_s
                FROM race_entries
                WHERE finish_pos = 1 AND race_time_s IS NOT NULL
                ORDER BY race_key, horse_no
            ) w ON w.race_key = r.race_key
            WHERE r.race_s3f IS NOT NULL
              AND r.race_l3f IS NOT NULL
              AND r.status = 'result'
            """
        )
    ).fetchall()
    return [
        _LapRow(str(k), str(d), str(tt), int(dist), float(s3), float(l3), float(wt))
        for k, d, tt, dist, s3, l3, wt in rows
    ]


def _print_lap_integrity(rows: list[_LapRow]) -> list[_LapRow]:
    """S3・L3・走破タイムが同一レースとして整合するか検査し、整合分だけ返す。

    式の比較は「3者が同じレースの値である」ことが前提。前提が崩れたレースを混ぜると、
    式の乖離ではなくデータ不整合を測ってしまう。
    """
    print("\n" + "=" * 78)
    print("■ 前提チェック: S3・L3・走破タイムが同一レースとして整合するか")
    print("=" * 78)

    checkable = [(r.implied_mid_pace, r) for r in rows if r.implied_mid_pace is not None]
    if not checkable:
        print("  中間区間を持つレースがなく、検査できません。")
        return rows

    paces = sorted(p for p, _ in checkable if p is not None)
    n = len(paces)
    print(f"  検査対象（中間区間を持つ距離）: {n:,}件")
    print(
        f"  中間区間の逆算ペース(秒/F)  最小 {paces[0]:.2f}"
        f"  5% {_percentile(paces, 0.05):.2f}  中央 {_percentile(paces, 0.50):.2f}"
        f"  95% {_percentile(paces, 0.95):.2f}  最大 {paces[-1]:.2f}"
    )

    broken = [
        (p, r)
        for p, r in checkable
        if p is not None and not _PLAUSIBLE_MID_LO <= p <= _PLAUSIBLE_MID_HI
    ]
    ok_count = n - len(broken)
    print(
        f"  整合（{_PLAUSIBLE_MID_LO:.0f}〜{_PLAUSIBLE_MID_HI:.0f}秒/F）: {ok_count:,}件"
        f"（{ok_count / n:.1%}） / 不整合: {len(broken):,}件（{len(broken) / n:.1%}）"
    )

    if broken:
        print("\n  不整合レースの例（逆算ペースが極端な順に10件）")
        print(
            f"    {'レースキー':<18}{'日付':<12}{'距離':>8}{'S3':>7}{'L3':>7}"
            f"{'勝ちタイム':>11}{'中間秒/F':>10}"
        )
        for p, r in sorted(broken, key=lambda x: -abs(x[0] - 12.0))[:10]:
            print(
                f"    {r.race_key:<18}{r.race_date:<12}{r.distance_m:>7}m"
                f"{r.s3f:>7.1f}{r.l3f:>7.1f}{r.winner_time:>11.1f}{p:>10.2f}"
            )
        print(
            "\n  ※ 中間だけが両端と大きく異なるのは競走として起こらない。"
            "\n  ※ S3/L3 と勝ちタイムのどちらかが別レース由来か誤読の疑いがある。"
            "\n  ※ 以降の式比較はこれらを除外して集計する。"
        )

    broken_keys = {r.race_key for _, r in broken}
    return [r for r in rows if r.race_key not in broken_keys]


def _build_samples(rows: list[_LapRow]) -> tuple[list[_FormulaSample], int]:
    samples: list[_FormulaSample] = []
    skipped = 0
    for r in rows:
        try:
            current = calculate_rpci_from_lap(Furlong3Time(r.s3f), Furlong3Time(r.l3f))
            target = calculate_rpci_target(
                RaceTime(r.winner_time), Furlong3Time(r.l3f), Distance(r.distance_m)
            )
        except ValueError:
            # 上がり3F ≧ 走破タイム 等、VOの検証を通らない値は比較対象から外す。
            skipped += 1
            continue
        samples.append(
            _FormulaSample(
                row=r,
                current=current,
                target=target,
                current_label=str(classify_pace(current, r.track_type)),
                target_label=str(classify_pace(target, r.track_type)),
            )
        )
    return samples, skipped


def _print_group_table(title: str, groups: list[tuple[str, list[_FormulaSample]]]) -> None:
    print(f"\n  {title}")
    print(f"    {'区分':<12}{'件数':>8}{'平均差':>10}{'絶対差平均':>12}{'区分変化':>10}")
    for label, grp in groups:
        if not grp:
            continue
        diffs = [s.diff for s in grp]
        changed = sum(1 for s in grp if s.label_changed)
        print(
            f"    {label:<12}{len(grp):>8,}{sum(diffs) / len(grp):>+10.3f}"
            f"{sum(abs(d) for d in diffs) / len(grp):>12.3f}{changed / len(grp):>9.1%}"
        )


def _print_formula_diff(samples: list[_FormulaSample], skipped: int) -> None:
    n = len(samples)
    diffs = [s.diff for s in samples]
    abs_diffs = sorted(abs(d) for d in diffs)
    changed = [s for s in samples if s.label_changed]

    print(f"  対象レース: {n:,}件（VO検証で除外 {skipped:,}件）")
    print(
        f"  差(TARGET式 − 現行式) 平均 {sum(diffs) / n:+.3f}  絶対差 平均 {sum(abs_diffs) / n:.3f}"
    )
    print(
        f"  絶対差 中央値 {_percentile(abs_diffs, 0.50):.2f}"
        f"  90%点 {_percentile(abs_diffs, 0.90):.2f}"
        f"  99%点 {_percentile(abs_diffs, 0.99):.2f}"
        f"  最大 {abs_diffs[-1]:.2f}"
    )
    print(f"  ペース区分が変わるレース: {len(changed):,}件（{len(changed) / n:.1%}）")

    bands = [(0, 1200), (1201, 1600), (1601, 2000), (2001, 2400), (2401, 9999)]
    _print_group_table(
        "距離帯別（1200m以下は中間区間が無く、ほぼ一致するはず）",
        [
            (
                f"{lo}-{hi}m" if hi < 9999 else f"{lo}m以上",
                [s for s in samples if lo <= s.row.distance_m <= hi],
            )
            for lo, hi in bands
        ],
    )
    _print_group_table(
        "コース種別別",
        [
            (track, [s for s in samples if s.row.track_type == track])
            for track in sorted({s.row.track_type for s in samples})
        ],
    )
    # 現行式は前半3Fを常に600m扱いする。1300m等の端数距離では実際500mなので
    # 前半を実際より速いと誤認し、距離帯とは別の要因で大きく外れる。
    _print_group_table(
        "先頭区間の端数別（現行式は前半3Fを常に600m扱いする）",
        [
            (
                "端数なし(600m)",
                [s for s in samples if s.row.s3_distance_m == 600],
            ),
            (
                "端数あり(500m)",
                [s for s in samples if s.row.s3_distance_m != 600],
            ),
        ],
    )

    print("\n  区分変化の内訳（現行 → TARGET式）")
    transitions: dict[str, int] = {}
    for s in changed:
        key = f"{s.current_label} → {s.target_label}"
        transitions[key] = transitions.get(key, 0) + 1
    for name, count in sorted(transitions.items(), key=lambda kv: -kv[1]):
        print(f"    {name:<20}{count:>8,}件（全体の {count / n:.1%}）")


def _print_rpci_formula_comparison(session: Session) -> None:
    """現行のRPCI式と、TARGET のレースPCI に一致する式の乖離を実測する。

    現行 `calculate_rpci_from_lap` は前半3Fと後半3Fだけを仮想1200mへ射影するため、
    中間区間を捨てている。TARGET は個馬PCIと同じ式をレース自身へ適用しており、
    1200m超では系統的に乖離する（1200m戦では両式が一致する）。

    置き換えは全レース再計算・ペース区分閾値の再較正・RPCIモデル再学習を伴うため、
    まず「どれだけ動くか」「区分が変わるレースがどれだけあるか」を測る。
    ただし保存値そのものが壊れているレースを混ぜると式の差を測れないため、
    先に S3・L3・走破タイムの整合を検査して切り分ける。
    """
    rows = _fetch_lap_rows(session)
    if not rows:
        print("\n  レースラップと勝ち馬タイムが揃うレースがありません。")
        return

    consistent = _print_lap_integrity(rows)

    print("\n" + "=" * 78)
    print("■ RPCI式の乖離実測: 現行(S3/L3を1200m射影) vs TARGET一致式(レース全体)")
    print("=" * 78)

    samples, skipped = _build_samples(consistent)
    if not samples:
        print("  比較可能なレースがありません。")
        return
    _print_formula_diff(samples, skipped)

    print(
        "\n  ※ 区分変化率が高いほど、式の置き換えには閾値の再較正とモデル再学習が要る。"
        "\n  ※ 本番設定は変更していない。この出力は判断材料のみ。"
    )


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session = build_session_maker(engine)()

    # ── 1. races.rpci_actual の分布 ──────────────────────────────────
    print("=" * 60)
    print("■ races.rpci_actual の分布")
    print("=" * 60)

    total_stmt = (
        select(func.count()).select_from(RaceModel).where(RaceModel.rpci_actual.is_not(None))
    )
    total = session.scalar(total_stmt) or 0
    print(f"  rpci_actual 非NULL レース数: {total:,}")

    if total == 0:
        print("  データなし。")
        return

    # min/max/avg
    stats_stmt = select(
        func.min(RaceModel.rpci_actual),
        func.max(RaceModel.rpci_actual),
        func.avg(RaceModel.rpci_actual),
    ).where(RaceModel.rpci_actual.is_not(None))
    mn, mx, avg = session.execute(stats_stmt).one()
    print(f"  最小: {mn:.2f}  最大: {mx:.2f}  平均: {avg:.2f}")

    # 分位数（PostgreSQL）
    try:
        pct_result = session.execute(
            text(
                """
                SELECT
                    percentile_cont(0.05) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.25) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.50) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.75) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.99) WITHIN GROUP (ORDER BY rpci_actual)
                FROM races
                WHERE rpci_actual IS NOT NULL
                """
            )
        ).one()
        p5, p25, p50, p75, p95, p99 = pct_result
        print(f"  5%  : {p5:.2f}")
        print(f"  25% : {p25:.2f}")
        print(f"  中央: {p50:.2f}")
        print(f"  75% : {p75:.2f}")
        print(f"  95% : {p95:.2f}")
        print(f"  99% : {p99:.2f}")
    except Exception as exc:
        print(f"  分位数取得エラー（PostgreSQL 未接続？）: {exc}")

    # 外れ値件数
    outlier_count_stmt = (
        select(func.count())
        .select_from(RaceModel)
        .where(
            RaceModel.rpci_actual.is_not(None),
            (RaceModel.rpci_actual < args.rpci_min) | (RaceModel.rpci_actual > args.rpci_max),
        )
    )
    outliers = session.scalar(outlier_count_stmt) or 0
    pct_out = outliers / total * 100
    print(
        f"\n  ── 外れ値: {outliers:,} レース（{pct_out:.1f}%）"
        f"が {args.rpci_min}〜{args.rpci_max} 範囲外"
    )

    # 年別集計
    print("\n  ── 年別 外れ値率")
    year_stmt = text(
        f"""
        SELECT
            EXTRACT(YEAR FROM race_date)::int AS yr,
            COUNT(*) AS total,
            SUM(CASE
                WHEN rpci_actual < {args.rpci_min}
                  OR rpci_actual > {args.rpci_max}
                THEN 1 ELSE 0 END) AS outliers,
            MIN(rpci_actual), MAX(rpci_actual), AVG(rpci_actual)
        FROM races
        WHERE rpci_actual IS NOT NULL
        GROUP BY yr
        ORDER BY yr
        """
    )
    try:
        for row in session.execute(year_stmt):
            yr, tot, out, mn_y, mx_y, avg_y = row
            pct = out / tot * 100 if tot else 0
            print(
                f"    {yr}年: {tot:5d}件 外れ値{out:5d}({pct:5.1f}%) "
                f"min={mn_y:.1f} max={mx_y:.1f} avg={avg_y:.1f}"
            )
    except Exception as exc:
        print(f"    年別集計エラー: {exc}")

    # ── 2. コース種別別の rpci_actual 分布 ──────────────────────────────
    print("\n  ── コース種別別 rpci_actual 分布")
    track_stmt = text(
        """
        SELECT
            track_type,
            COUNT(*)                                                AS cnt,
            ROUND(MIN(rpci_actual)::numeric, 1)                    AS mn,
            ROUND(MAX(rpci_actual)::numeric, 1)                    AS mx,
            ROUND(AVG(rpci_actual)::numeric, 1)                    AS avg,
            ROUND(percentile_cont(0.50)
                  WITHIN GROUP (ORDER BY rpci_actual)::numeric, 1) AS p50,
            SUM(CASE
                WHEN rpci_actual < :lo OR rpci_actual > :hi
                THEN 1 ELSE 0 END)                                 AS outliers
        FROM races
        WHERE status = 'result'
          AND rpci_actual IS NOT NULL
        GROUP BY track_type
        ORDER BY track_type
        """
    )
    try:
        hdr = f"  {'種別':6s} {'件数':>7s} {'最小':>7s} {'最大':>7s}"
        hdr += f" {'平均':>7s} {'中央':>7s} {'外れ値':>8s}"
        print(hdr)
        for row in session.execute(track_stmt, {"lo": args.rpci_min, "hi": args.rpci_max}):
            tt, cnt, mn_t, mx_t, avg_t, p50_t, out_t = row
            out_pct = out_t / cnt * 100 if cnt else 0
            print(
                f"  {tt:6s} {cnt:7,d} {mn_t:7.1f} {mx_t:7.1f} "
                f"{avg_t:7.1f} {p50_t:7.1f} {out_t:5,d}({out_pct:4.1f}%)"
            )
    except Exception as exc:
        print(f"    種別集計エラー: {exc}")

    # ── 4. race_entries.pci_actual の分布 ────────────────────────────
    print("\n" + "=" * 60)
    print("■ race_entries.pci_actual の分布")
    print("=" * 60)

    entry_stats = select(
        func.count(),
        func.min(RaceEntryModel.pci_actual),
        func.max(RaceEntryModel.pci_actual),
        func.avg(RaceEntryModel.pci_actual),
    ).where(RaceEntryModel.pci_actual.is_not(None))
    n_entries, mn_e, mx_e, avg_e = session.execute(entry_stats).one()
    print(f"  pci_actual 非NULL エントリ: {n_entries:,}")
    if n_entries:
        print(f"  最小: {mn_e:.2f}  最大: {mx_e:.2f}  平均: {avg_e:.2f}")
        try:
            pct_e = session.execute(
                text(
                    """
                    SELECT
                        percentile_cont(0.05) WITHIN GROUP (ORDER BY pci_actual),
                        percentile_cont(0.25) WITHIN GROUP (ORDER BY pci_actual),
                        percentile_cont(0.50) WITHIN GROUP (ORDER BY pci_actual),
                        percentile_cont(0.75) WITHIN GROUP (ORDER BY pci_actual),
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY pci_actual)
                    FROM race_entries
                    WHERE pci_actual IS NOT NULL
                    """
                )
            ).one()
            ep5, ep25, ep50, ep75, ep95 = pct_e
            print(
                f"  5%:  {ep5:.2f}  25%: {ep25:.2f}  中央: {ep50:.2f}"
                f"  75%: {ep75:.2f}  95%: {ep95:.2f}"
            )
        except Exception as exc:
            print(f"  分位数取得エラー: {exc}")

    # ── 4b. コース種別×年の分布（中立点の妥当性診断） ────────────────
    if args.compare_rpci_formula:
        _print_rpci_formula_comparison(session)
        return

    if args.by_track_year:
        try:
            _print_track_year_distribution(
                session, args.rpci_min, args.rpci_max, args.month_from, args.month_to
            )
        except Exception as exc:
            print(f"  コース種別×年 集計エラー: {exc}")

    # ── 5. 外れ値レース詳細 ──────────────────────────────────────────
    if args.show_outliers:
        print("\n" + "=" * 60)
        print(f"■ rpci_actual が {args.rpci_min} 未満 / {args.rpci_max} 超のレース（上位 50 件）")
        print("=" * 60)
        detail_stmt = (
            select(
                RaceModel.race_key,
                RaceModel.race_date,
                RaceModel.distance_m,
                RaceModel.track_type,
                RaceModel.rpci_actual,
            )
            .where(
                RaceModel.rpci_actual.is_not(None),
                (RaceModel.rpci_actual < args.rpci_min) | (RaceModel.rpci_actual > args.rpci_max),
            )
            .order_by(func.abs(RaceModel.rpci_actual - 50).desc())
            .limit(50)
        )
        rows = session.execute(detail_stmt).all()
        if not rows:
            print("  外れ値なし。")
        else:
            print(f"  {'レースキー':18s} {'日付':12s} {'距離':6s} {'馬場':6s} {'rpci_actual':>12s}")
            for rk, rd, dist, tt, rv in rows:
                print(f"  {rk:18s} {str(rd):12s} {dist:6d} {tt:6s} {rv:12.2f}")

    # ── 6. バックテスト有効サンプル数の推定 ───────────────────────────
    print("\n" + "=" * 60)
    print(f"■ バックテスト有効範囲（{args.rpci_min}〜{args.rpci_max}）のみで推定精度")
    print("=" * 60)
    valid_stmt = text(
        f"""
        SELECT COUNT(*)
        FROM races
        WHERE status = 'result'
          AND rpci_actual IS NOT NULL
          AND rpci_actual >= {args.rpci_min}
          AND rpci_actual <= {args.rpci_max}
        """
    )
    try:
        valid_count = session.execute(valid_stmt).scalar() or 0
        invalid_count = (
            session.execute(
                text(
                    f"""
                SELECT COUNT(*)
                FROM races
                WHERE status = 'result'
                  AND rpci_actual IS NOT NULL
                  AND (rpci_actual < {args.rpci_min} OR rpci_actual > {args.rpci_max})
                """
                )
            ).scalar()
            or 0
        )
        print(f"  有効: {valid_count:,} / 外れ値: {invalid_count:,}")
        if valid_count + invalid_count > 0:
            ratio = invalid_count / (valid_count + invalid_count) * 100
            print(f"  外れ値は全確定レースの {ratio:.1f}% を占める")
    except Exception as exc:
        print(f"  集計エラー: {exc}")

    print()


if __name__ == "__main__":
    main()
