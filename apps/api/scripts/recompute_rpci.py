"""races.rpci_actual を TARGET 一致式へ移行する。

現行 `calculate_rpci_from_lap` には独立した2つの誤りがある（docs/DECISIONS.md ADR-2026-08-04）:

  1. 中間区間を捨てる    … 前半3Fと後半3Fだけを仮想1200mへ射影するため、1200m超で
                            系統的にずれる。距離が伸びるほど拡大する。
  2. 前半3Fを常に600m扱い … JRAのハロンタイムは距離が200mで割り切れない場合だけ
                            先頭区間が端数になる（1300m = 100m + 200m×6）ため、
                            端数距離では前半3Fが実際は500m。前半を実際より速い＝
                            ハイ寄りと誤認する。

実測（全15,332レース）:
    端数なし(600m) 13,503件  平均差 +0.905  区分変化 16.5%
    端数あり(500m)  1,829件  平均差 +17.252 区分変化 97.3%（誤差の向きが常に同じ）

TARGET一致式 `calculate_rpci_target` は 総タイム・L3（端数は先頭にあるため常に600m）・
距離だけを使うため、どちらの誤りも受けない。

分布が動くのでペース区分の閾値も再較正が要る。既定は dry-run で、
新しい分布と「現在のラベル構成比を保つ閾値」を提示するだけで DB は変更しない。

使い方:
    cd apps/api
    python -m scripts.recompute_rpci               # 影響を確認（DBは変更しない）
    python -m scripts.recompute_rpci --apply       # races.rpci_actual を書き換える
"""

from __future__ import annotations

import argparse
import sys
from typing import NamedTuple

sys.path.insert(0, "src")

from sqlalchemy import text
from sqlalchemy.orm import Session

from pci.config.settings import get_settings
from pci.domain.pace.pci import calculate_rpci_target
from pci.domain.pace.rpci_forecast import DEFAULT_WEIGHTS, PaceLabel, classify_pace
from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime
from pci.infrastructure.database.session import build_engine, build_session_maker

_TRACKS = ("芝", "ダート")


class _Recomputed(NamedTuple):
    race_key: str
    track_type: str
    old_rpci: float
    new_rpci: float


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="races.rpci_actual を TARGET 一致式へ移行する")
    p.add_argument(
        "--apply",
        action="store_true",
        help="DBを実際に書き換える（未指定時は影響の確認のみ）",
    )
    return p.parse_args()


def _percentile(sorted_values: list[float], q: float) -> float:
    return sorted_values[min(len(sorted_values) - 1, int(len(sorted_values) * q))]


def _collect(session: Session) -> list[_Recomputed]:
    """レースラップと勝ち馬タイムが揃う確定レースを新式で再計算する。

    レース走破タイムは勝ち馬のタイムを使う（TARGET のレースPCI と同じ定義）。
    ラップが無いレースは全完走馬PCI平均のフォールバックのままで、この移行の対象外。
    """
    rows = session.execute(
        text(
            """
            SELECT r.race_key, r.track_type, r.distance_m,
                   r.rpci_actual, r.race_l3f, w.race_time_s
            FROM races r
            JOIN (
                SELECT DISTINCT ON (race_key) race_key, race_time_s
                FROM race_entries
                WHERE finish_pos = 1 AND race_time_s IS NOT NULL
                ORDER BY race_key, horse_no
            ) w ON w.race_key = r.race_key
            WHERE r.race_s3f IS NOT NULL
              AND r.race_l3f IS NOT NULL
              AND r.rpci_actual IS NOT NULL
              AND r.status = 'result'
            """
        )
    ).fetchall()

    out: list[_Recomputed] = []
    skipped = 0
    for race_key, track_type, distance_m, old_rpci, l3f, winner_time in rows:
        try:
            new_rpci = calculate_rpci_target(
                RaceTime(float(winner_time)),
                Furlong3Time(float(l3f)),
                Distance(int(distance_m)),
            )
        except ValueError:
            skipped += 1
            continue
        out.append(_Recomputed(str(race_key), str(track_type), float(old_rpci), new_rpci))
    if skipped:
        print(f"  ※ VO検証を通らず除外: {skipped:,}件")
    return out


def _label_shares(values: list[float], track_type: str) -> dict[str, float]:
    counts = {str(label): 0 for label in PaceLabel}
    for v in values:
        counts[str(classify_pace(v, track_type))] += 1
    total = len(values) or 1
    return {label: count / total for label, count in counts.items()}


def _thresholds_for_shares(
    values: list[float], high_share: float, slow_share: float
) -> tuple[float, float]:
    """指定した構成比になる閾値を、分布の分位点から求める。"""
    ordered = sorted(values)
    high = _percentile(ordered, high_share)
    slow = _percentile(ordered, 1.0 - slow_share)
    return round(high, 1), round(slow, 1)


def _report(samples: list[_Recomputed]) -> None:
    print("\n" + "=" * 78)
    print("■ 再計算の影響")
    print("=" * 78)
    print(f"  対象レース: {len(samples):,}件")

    for track in _TRACKS:
        grp = [s for s in samples if s.track_type == track]
        if not grp:
            continue
        old_vals = [s.old_rpci for s in grp]
        new_vals = [s.new_rpci for s in grp]
        old_sorted, new_sorted = sorted(old_vals), sorted(new_vals)
        old_shares = _label_shares(old_vals, track)
        new_shares = _label_shares(new_vals, track)
        changed = sum(
            1 for s in grp if classify_pace(s.old_rpci, track) != classify_pace(s.new_rpci, track)
        )
        cur_hi, cur_sl = (
            (DEFAULT_WEIGHTS.dirt_high_threshold, DEFAULT_WEIGHTS.dirt_slow_threshold)
            if track == "ダート"
            else (DEFAULT_WEIGHTS.high_threshold, DEFAULT_WEIGHTS.slow_threshold)
        )
        print(f"\n  ── {track}（{len(grp):,}件）")
        print(
            f"    分布   旧: 平均 {sum(old_vals) / len(grp):.2f}"
            f" 中央 {_percentile(old_sorted, 0.5):.2f}"
            f"  →  新: 平均 {sum(new_vals) / len(grp):.2f}"
            f" 中央 {_percentile(new_sorted, 0.5):.2f}"
        )
        print(f"    ペース区分が変わるレース: {changed:,}件（{changed / len(grp):.1%}）")
        print(f"    {'ラベル構成比':<14}{'旧':>10}{'新(現閾値)':>14}")
        for label in (PaceLabel.HIGH, PaceLabel.AVERAGE, PaceLabel.SLOW):
            key = str(label)
            print(f"    {key:<14}{old_shares[key]:>9.1%}{new_shares[key]:>13.1%}")
        _print_threshold_candidates(new_vals, old_shares, (cur_hi, cur_sl))


def _print_threshold_candidates(
    new_values: list[float],
    old_shares: dict[str, float],
    current: tuple[float, float],
) -> None:
    """閾値の候補を、それぞれの結果ラベル構成比と並べて提示する。

    どれを採るかは仕様判断なのでスクリプトでは決めない。特に「旧構成比を保つ」案は
    旧構成比自体がバグの産物である点に注意が要る（端数距離1,829件が一律ハイ寄りへ
    誤判定されていた。docs/DECISIONS.md ADR-2026-08-04）。
    """
    high_ratio = old_shares[str(PaceLabel.HIGH)]
    slow_ratio = old_shares[str(PaceLabel.SLOW)]
    candidates: list[tuple[str, tuple[float, float], str]] = [
        ("現行据え置き", current, "式だけ直し閾値は変えない"),
        (
            "旧構成比を保つ",
            _thresholds_for_shares(new_values, high_ratio, slow_ratio),
            "※旧構成比はバグ由来の偏りを含む",
        ),
        ("3分位(各33%)", _thresholds_for_shares(new_values, 1 / 3, 1 / 3), "3ラベルを等頻度にする"),
        ("イーブン基準50±2", (48.0, 52.0), "RPCI=50(前後同ペース)を意味の基準にする"),
    ]

    print(
        f"    {'閾値候補':<18}{'ハイ<':>8}{'スロー>':>9}"
        f"{'ハイ%':>8}{'平均%':>8}{'スロー%':>9}  補足"
    )
    for name, (hi, sl), note in candidates:
        n = len(new_values)
        high_n = sum(1 for v in new_values if v < hi)
        slow_n = sum(1 for v in new_values if v > sl)
        avg_n = n - high_n - slow_n
        print(
            f"    {name:<18}{hi:>8.1f}{sl:>9.1f}"
            f"{high_n / n:>7.1%}{avg_n / n:>8.1%}{slow_n / n:>8.1%}  {note}"
        )


def _apply(session: Session, samples: list[_Recomputed]) -> None:
    updated = 0
    for s in samples:
        if s.old_rpci == s.new_rpci:
            continue
        session.execute(
            text("UPDATE races SET rpci_actual = :v WHERE race_key = :k"),
            {"v": s.new_rpci, "k": s.race_key},
        )
        updated += 1
    session.commit()
    print(f"\n  races.rpci_actual を {updated:,}件 更新しました。")
    print("  次に必要な作業:")
    print("    1. ペース区分の閾値を再較正する（上の閾値案を ADR で確定してから反映）")
    print("    2. RPCIモデルを再学習する（学習ラベルが変わったため）")
    print("    3. バックテストで再評価する")


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session = build_session_maker(engine)()

    samples = _collect(session)
    if not samples:
        print("再計算対象のレースがありません。")
        return

    _report(samples)

    if args.apply:
        _apply(session, samples)
    else:
        print(
            "\n  DBは変更していません（dry-run）。"
            "\n  書き換えるには --apply を付けて再実行してください。"
            "\n  ※ 実行前にDBのバックアップを取ること。閾値とモデルの更新もセットで必要。"
        )


if __name__ == "__main__":
    main()
