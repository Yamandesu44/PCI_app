#!/usr/bin/env python3
"""開発用データシードスクリプト。

fixture データを PostgreSQL に投入し、フルスタック E2E を可能にする。
何度実行しても同じ結果（冪等）。

使い方:
    cd apps/api

    # DB 起動 & マイグレーション（初回のみ）
    docker-compose -f ../../docker-compose.yml up -d db
    alembic upgrade head

    # シード（追記・冪等）
    python scripts/seed_dev.py

    # 全クリアして再シード
    python scripts/seed_dev.py --reset

シード後の確認 URL:
    http://localhost:3000/races/2026062005010101/forecast       （展開予想）
    http://localhost:3000/races/2026061705010101/pace-analysis  （確定後ペース分析）
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

# apps/api/src を import パスへ追加
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from pci.config.settings import Settings
from pci.domain.pace.pci import aggregate_rpci, calculate_pci
from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime
from pci.infrastructure.database.models import (
    HorseModel,
    JockeyModel,
    RaceEntryModel,
    RaceModel,
    TrainerModel,
)

# ---------------------------------------------------------------------------
# レースキー（apps/web/src/app/page.tsx と合わせる）
# ---------------------------------------------------------------------------

UPCOMING_RACE_KEY = "2026062005010101"   # 2026-06-20 東京1回1日目1R（出走前）
CONFIRMED_RACE_KEY = "2026061705010101"  # 2026-06-17 東京1回1日目1R（確定後）

# ---------------------------------------------------------------------------
# マスタデータ
# ---------------------------------------------------------------------------

_JOCKEYS = [
    {"code": "JKY001", "name": "田中太郎"},
    {"code": "JKY002", "name": "鈴木次郎"},
]

_TRAINERS = [
    {"code": "TRN001", "name": "山田三郎"},
    {"code": "TRN002", "name": "中村四郎"},
]

# ---------------------------------------------------------------------------
# 出走前レースの馬データ
# 5走分の4角通過順位 (c4_history) で脚質を設計:
#   逃げ: 1〜2番手率 >= 60% / 先行: 3〜5番手 >= 60%
#   差し: 6〜9番手 >= 60% / 追込: 10番手以降 >= 60%
# ---------------------------------------------------------------------------
# (ketto_num, name, sex, birth_year, c4_history[5走分・最新順])
_UPCOMING_HORSES = [
    ("2023000001", "フウライボー", "牡", 2023, [1, 1, 2, 1, 1]),      # 逃げ  100%
    ("2023000002", "カゼノコ",   "牝", 2023, [3, 3, 4, 4, 3]),      # 先行  100%
    ("2023000003", "ミチシルベ", "牡", 2023, [4, 4, 3, 5, 4]),      # 先行  100%
    ("2023000004", "アゲアシ",   "牡", 2023, [6, 7, 6, 6, 7]),      # 差し  100%
    ("2023000005", "ハナイキ",   "牝", 2023, [7, 8, 7, 8, 7]),      # 差し  100%
    ("2023000006", "オソカラ",   "牡", 2023, [8, 7, 8, 7, 6]),      # 差し  100%
    ("2023000007", "ドベドベ",   "牝", 2023, [12, 11, 10, 12, 11]), # 追込  100%
    ("2023000008", "キマグレ",   "牡", 2023, [2, 6, 4, 8, 3]),      # 自在（散らばり）
]

# 脚質判定の根拠となる過去5走スタブ（status=result が必要）
_HISTORY_RACES = [
    ("2026050505010101", datetime.date(2026, 5,  5)),
    ("2026051205010101", datetime.date(2026, 5, 12)),
    ("2026051905010101", datetime.date(2026, 5, 19)),
    ("2026052605010101", datetime.date(2026, 5, 26)),
    ("2026060205010101", datetime.date(2026, 6,  2)),
]

# ---------------------------------------------------------------------------
# 確定後レースの馬・成績データ（1600m芝・スロー展開・先行有利）
# ---------------------------------------------------------------------------
# (ketto_num, name, sex, birth_year)
_CONFIRMED_HORSES = [
    ("2022000001", "スロートップ",   "牡", 2022),
    ("2022000002", "スローセカンド", "牝", 2022),
    ("2022000003", "スローサード",   "牡", 2022),
    ("2022000004", "スローフォース", "牡", 2022),
    ("2022000005", "ハナドタ",       "牝", 2022),
    ("2022000006", "オシマイ",       "牡", 2022),
]

# (ketto_num, horse_no, frame_no, finish_pos, race_time_s, agari_3f_s,
#  corner_1, corner_2, corner_3, corner_4, running_style)
_CONFIRMED_RESULTS = [
    ("2022000001", 1, 1, 1, 96.5, 34.5, 2, 2, 2, 2, "先行"),  # 先行が勝利 → スロー
    ("2022000002", 2, 1, 2, 96.8, 34.3, 5, 5, 4, 4, "差し"),
    ("2022000003", 3, 2, 3, 97.0, 34.2, 6, 6, 5, 5, "差し"),
    ("2022000004", 4, 2, 4, 97.3, 34.0, 7, 7, 7, 6, "差し"),
    ("2022000005", 5, 3, 5, 97.5, 35.5, 1, 1, 1, 1, "逃げ"),  # 逃げ馬は後退
    ("2022000006", 6, 3, 6, 97.8, 34.8, 8, 8, 8, 7, "追込"),  # 追込は届かず
]
_CONFIRMED_DISTANCE_M = 1600

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _pci(race_time_s: float, agari_3f_s: float, distance_m: int) -> float:
    return calculate_pci(
        RaceTime(race_time_s),
        Furlong3Time(agari_3f_s),
        Distance(distance_m),
    ).value


def _jockey(horse_no: int) -> str:
    return "JKY001" if horse_no % 2 == 1 else "JKY002"


def _trainer(horse_no: int, boundary: int = 4) -> str:
    return "TRN001" if horse_no <= boundary else "TRN002"


# ---------------------------------------------------------------------------
# シード関数
# ---------------------------------------------------------------------------


def _seed_masters(s: Session) -> None:
    print("  騎手・調教師マスタ を投入中...")
    for j in _JOCKEYS:
        s.merge(JockeyModel(code=j["code"], name=j["name"]))
    for t in _TRAINERS:
        s.merge(TrainerModel(code=t["code"], name=t["name"]))
    s.flush()


def _seed_horses(s: Session) -> None:
    print("  馬マスタ を投入中...")
    for ketto, name, sex, birth_year, _ in _UPCOMING_HORSES:
        s.merge(HorseModel(ketto_num=ketto, name=name, sex=sex, birth_year=birth_year))
    for ketto, name, sex, birth_year in _CONFIRMED_HORSES:
        s.merge(HorseModel(ketto_num=ketto, name=name, sex=sex, birth_year=birth_year))
    s.flush()


def _seed_history(s: Session) -> None:
    print(f"  過去レース {len(_HISTORY_RACES)} 件（脚質判定用スタブ）を投入中...")
    for race_key, race_date in _HISTORY_RACES:
        s.merge(
            RaceModel(
                race_key=race_key,
                race_date=race_date,
                jyo_cd="05",
                distance_m=1800,
                track_type="芝",
                field_size=len(_UPCOMING_HORSES),
                status="result",
                track_condition="良",
                weather="晴",
                grade=None,
                race_class="3歳未勝利",
                rpci_actual=None,
                pci3_actual=None,
            )
        )
    s.flush()

    print(f"  過去出走成績（{len(_UPCOMING_HORSES)} 頭 × {len(_HISTORY_RACES)} 走）を投入中...")
    for race_idx, (race_key, _) in enumerate(_HISTORY_RACES):
        for horse_no, (ketto, _, _, _, c4_history) in enumerate(_UPCOMING_HORSES, start=1):
            s.merge(
                RaceEntryModel(
                    race_key=race_key,
                    horse_no=horse_no,
                    frame_no=horse_no,
                    ketto_num=ketto,
                    weight=460.0,
                    jockey_code=_jockey(horse_no),
                    trainer_code=_trainer(horse_no),
                    finish_pos=horse_no,
                    race_time_s=None,
                    agari_3f_s=None,
                    corner_1=None,
                    corner_2=None,
                    corner_3=None,
                    corner_4=c4_history[race_idx],
                    pci_actual=None,
                    running_style=None,
                )
            )
    s.flush()


def _seed_upcoming(s: Session) -> None:
    print(f"  出走前レース ({UPCOMING_RACE_KEY}) を投入中...")
    s.merge(
        RaceModel(
            race_key=UPCOMING_RACE_KEY,
            race_date=datetime.date(2026, 6, 20),
            jyo_cd="05",
            distance_m=1800,
            track_type="芝",
            field_size=len(_UPCOMING_HORSES),
            status="entries",
            track_condition="良",
            weather="晴",
            grade=None,
            race_class="3歳未勝利",
            rpci_actual=None,
            pci3_actual=None,
        )
    )
    s.flush()

    for horse_no, (ketto, _, _, _, _) in enumerate(_UPCOMING_HORSES, start=1):
        s.merge(
            RaceEntryModel(
                race_key=UPCOMING_RACE_KEY,
                horse_no=horse_no,
                frame_no=horse_no,
                ketto_num=ketto,
                weight=460.0,
                jockey_code=_jockey(horse_no),
                trainer_code=_trainer(horse_no),
                finish_pos=None,
                race_time_s=None,
                agari_3f_s=None,
                corner_1=None,
                corner_2=None,
                corner_3=None,
                corner_4=None,
                pci_actual=None,
                running_style=None,
            )
        )
    s.flush()


def _seed_confirmed(s: Session) -> tuple[float | None, float | None]:
    print(f"  確定後レース ({CONFIRMED_RACE_KEY}) を PCI 算出込みで投入中...")
    pci_values: list[float] = []
    finish_positions: list[int] = []

    for ketto, horse_no, frame_no, finish_pos, rt_s, a3f_s, c1, c2, c3, c4, rs in _CONFIRMED_RESULTS:
        pci = _pci(rt_s, a3f_s, _CONFIRMED_DISTANCE_M)
        pci_values.append(pci)
        finish_positions.append(finish_pos)
        s.merge(
            RaceEntryModel(
                race_key=CONFIRMED_RACE_KEY,
                horse_no=horse_no,
                frame_no=frame_no,
                ketto_num=ketto,
                weight=460.0,
                jockey_code=_jockey(horse_no),
                trainer_code=_trainer(horse_no, boundary=3),
                finish_pos=finish_pos,
                race_time_s=rt_s,
                agari_3f_s=a3f_s,
                corner_1=c1,
                corner_2=c2,
                corner_3=c3,
                corner_4=c4,
                pci_actual=pci,
                running_style=rs,
            )
        )

    rpci_res = aggregate_rpci(pci_values, finish_positions)
    s.merge(
        RaceModel(
            race_key=CONFIRMED_RACE_KEY,
            race_date=datetime.date(2026, 6, 17),
            jyo_cd="05",
            distance_m=_CONFIRMED_DISTANCE_M,
            track_type="芝",
            field_size=len(_CONFIRMED_RESULTS),
            status="result",
            track_condition="良",
            weather="晴",
            grade=None,
            race_class="3歳未勝利",
            rpci_actual=rpci_res.rpci,
            pci3_actual=rpci_res.pci3,
        )
    )
    s.flush()
    return rpci_res.rpci, rpci_res.pci3


def seed(s: Session) -> None:
    _seed_masters(s)
    _seed_horses(s)
    _seed_history(s)
    _seed_upcoming(s)
    rpci, pci3 = _seed_confirmed(s)
    s.commit()
    _print_summary(rpci, pci3)


def _print_summary(rpci: float | None, pci3: float | None) -> None:
    print()
    print("=" * 60)
    print("シード完了")
    print("=" * 60)
    print()
    print(f"【出走前レース】  {UPCOMING_RACE_KEY}  1800m芝 8頭")
    styles = ["逃げ", "先行", "先行", "差し", "差し", "差し", "追込", "自在"]
    for i, (ketto, name, _, _, _) in enumerate(_UPCOMING_HORSES):
        print(f"  {i+1:2}. {name}（{styles[i]}）  {ketto}")
    print()
    print(f"【確定後レース】  {CONFIRMED_RACE_KEY}  1600m芝 6頭")
    print(f"  RPCI={rpci}  PCI3={pci3}  → スローペース（先行有利）")
    for ketto, hno, _, pos, rt, a3f, *_ in _CONFIRMED_RESULTS:
        pci = _pci(rt, a3f, _CONFIRMED_DISTANCE_M)
        name = next(n for k, n, *_ in _CONFIRMED_HORSES if k == ketto)
        print(f"  {pos}着 {hno}番 {name}  PCI={pci}  走破={rt}s 上がり={a3f}s")
    print()
    print("確認 URL:")
    print(f"  http://localhost:3000/races/{UPCOMING_RACE_KEY}/forecast")
    print(f"  http://localhost:3000/races/{CONFIRMED_RACE_KEY}/pace-analysis")


# ---------------------------------------------------------------------------
# リセット
# ---------------------------------------------------------------------------


def reset(s: Session) -> None:
    print("DB をリセット中（全テーブルを TRUNCATE）...")
    s.execute(
        text(
            "TRUNCATE TABLE "
            "pace_fit, predicted_pace, race_entries, races, "
            "horses, jockeys, trainers "
            "RESTART IDENTITY"
        )
    )
    s.commit()
    print("  ✓ リセット完了")


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="開発用データシードスクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="シード前に全テーブルをクリアする（既存データがすべて消える）",
    )
    args = parser.parse_args()

    settings = Settings()
    engine = create_engine(settings.database_url, echo=False)

    try:
        with Session(engine) as session:
            if args.reset:
                reset(session)
            seed(session)
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        print(
            "ヒント: docker-compose up -d db && alembic upgrade head を先に実行してください",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
