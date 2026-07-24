#!/usr/bin/env python3
"""開発用データシードスクリプト。

TARGET 取り込み後の状態に近い週次データを PostgreSQL に投入し、
フルスタック E2E を可能にする。
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
    http://localhost:3000/races/2026062809011111/forecast       （今週特別登録）
    http://localhost:3000/races/2026062109011111/pace-analysis  （先週結果）
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

UPCOMING_RACE_KEY = "2026062809011111"   # 2026-06-28 阪神11R（今週末・特別登録）
CONFIRMED_RACE_KEY = "2026062109011111"  # 2026-06-21 阪神11R（先週結果）

# ---------------------------------------------------------------------------
# マスタデータ
# ---------------------------------------------------------------------------

_JOCKEYS = [
    {"code": "TBD", "name": "騎手未定"},
    {"code": "JKY101", "name": "横山和生"},
    {"code": "JKY102", "name": "川田将雅"},
    {"code": "JKY103", "name": "戸崎圭太"},
    {"code": "JKY104", "name": "武豊"},
]

_TRAINERS = [
    {"code": "TRN101", "name": "上村洋行"},
    {"code": "TRN102", "name": "木村哲也"},
    {"code": "TRN103", "name": "友道康夫"},
    {"code": "TRN104", "name": "手塚貴久"},
    {"code": "TRN105", "name": "池江泰寿"},
    {"code": "TRN106", "name": "中竹和也"},
]

# ---------------------------------------------------------------------------
# 今週分の特別登録データ
# TARGET の特別登録では枠番・斤量・騎手が未確定のため、seed では仮番・0kg・騎手未定で保持する。
# 5走分の4角通過順位 (c4_history) で脚質を設計:
#   逃げ: 1〜2番手率 >= 60% / 先行: 3〜5番手 >= 60%
#   差し: 6〜9番手 >= 60% / 追込: 10番手以降 >= 60%
# ---------------------------------------------------------------------------
# (ketto_num, name, sex, birth_year, c4_history[5走分・最新順])
_UPCOMING_HORSES = [
    ("2021100001", "ベラジオオペラ", "牡", 2020, [2, 2, 3, 2, 2]),      # 逃げ寄り先行
    ("2021100002", "ロードデルレイ", "牡", 2020, [5, 5, 6, 5, 4]),      # 先行
    ("2021100003", "レガレイラ", "牝", 2021, [7, 8, 9, 7, 8]),          # 差し
    ("2021100004", "ジャスティンパレス", "牡", 2019, [10, 11, 10, 9, 11]), # 追込
    ("2021100005", "ソールオリエンス", "牡", 2020, [8, 9, 8, 7, 10]),   # 差し
    ("2021100006", "ドゥレッツァ", "牡", 2020, [4, 4, 5, 4, 3]),        # 先行
    ("2021100007", "プラダリア", "牡", 2019, [3, 4, 4, 3, 4]),          # 先行
    ("2021100008", "ローシャムパーク", "牡", 2019, [6, 6, 7, 5, 6]),    # 差し
    ("2021100009", "ディープボンド", "牡", 2017, [2, 3, 2, 3, 2]),      # 逃げ寄り先行
    ("2021100010", "ブローザホーン", "牡", 2019, [11, 10, 12, 11, 10]), # 追込
]

# 脚質判定の根拠となる過去5走スタブ（status=result が必要）
_HISTORY_RACES = [
    ("2026042609011001", datetime.date(2026, 4, 26)),
    ("2026050308011101", datetime.date(2026, 5, 3)),
    ("2026051005011101", datetime.date(2026, 5, 10)),
    ("2026053108011101", datetime.date(2026, 5, 31)),
    ("2026061409011101", datetime.date(2026, 6, 14)),
]

# ---------------------------------------------------------------------------
# 先週分の確定結果データ（TARGET RA/SE 取り込み相当）
# ---------------------------------------------------------------------------
# (ketto_num, name, sex, birth_year)
_CONFIRMED_HORSES = [
    ("2020100101", "サトノグランツ", "牡", 2020),
    ("2020100102", "シュヴァリエローズ", "牡", 2018),
    ("2020100103", "ヨーホーレイク", "牡", 2018),
    ("2020100104", "ボッケリーニ", "牡", 2016),
    ("2020100105", "マイネルエンペラー", "牡", 2020),
    ("2020100106", "ディープモンスター", "牡", 2018),
    ("2020100107", "ハヤヤッコ", "牡", 2016),
    ("2020100108", "メイショウブレゲ", "牡", 2019),
]

# (ketto_num, horse_no, frame_no, finish_pos, race_time_s, agari_3f_s,
#  corner_1, corner_2, corner_3, corner_4, running_style)
_CONFIRMED_RESULTS = [
    ("2020100103", 1, 1, 1, 132.8, 34.7, 6, 6, 5, 4, "差し"),
    ("2020100101", 2, 2, 2, 133.0, 35.0, 4, 4, 4, 3, "先行"),
    ("2020100105", 3, 3, 3, 133.2, 35.2, 2, 2, 2, 2, "先行"),
    ("2020100102", 4, 4, 4, 133.4, 34.9, 8, 8, 8, 7, "差し"),
    ("2020100106", 5, 5, 5, 133.6, 35.1, 7, 7, 7, 6, "差し"),
    ("2020100104", 6, 6, 6, 133.9, 35.8, 3, 3, 3, 5, "先行"),
    ("2020100107", 7, 7, 7, 134.1, 35.0, 10, 10, 10, 9, "追込"),
    ("2020100108", 8, 8, 8, 134.4, 35.4, 11, 11, 11, 10, "追込"),
]
_CONFIRMED_DISTANCE_M = 2200

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
    # 特別登録段階では騎手未定が多いため、出走前データは TBD を使う。
    return "TBD"


def _trainer(horse_no: int, boundary: int = 4) -> str:
    trainer_codes = ["TRN101", "TRN102", "TRN103", "TRN104", "TRN105", "TRN106"]
    return trainer_codes[(horse_no - 1) % len(trainer_codes)]


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
                jyo_cd="09",
                distance_m=2200,
                track_type="芝",
                field_size=len(_UPCOMING_HORSES),
                status="result",
                track_condition="良",
                weather="晴",
                grade="G1",
                race_class="TARGET直近5走",
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
    print(f"  今週特別登録レース ({UPCOMING_RACE_KEY}) を投入中...")
    s.merge(
        RaceModel(
            race_key=UPCOMING_RACE_KEY,
            race_date=datetime.date(2026, 6, 28),
            jyo_cd="09",
            distance_m=2200,
            track_type="芝",
            field_size=len(_UPCOMING_HORSES),
            status="entries",
            track_condition="良",
            weather="晴",
            grade="G1",
            race_class="宝塚記念 特別登録",
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
                frame_no=0,
                ketto_num=ketto,
                weight=0.0,
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
    print(f"  先週結果レース ({CONFIRMED_RACE_KEY}) を PCI 算出込みで投入中...")
    pci_values: list[float] = []
    finish_positions: list[int] = []

    for _, _, _, finish_pos, rt_s, a3f_s, *_ in _CONFIRMED_RESULTS:
        pci = _pci(rt_s, a3f_s, _CONFIRMED_DISTANCE_M)
        pci_values.append(pci)
        finish_positions.append(finish_pos)

    rpci_res = aggregate_rpci(pci_values, finish_positions)
    s.merge(
        RaceModel(
            race_key=CONFIRMED_RACE_KEY,
            race_date=datetime.date(2026, 6, 21),
            jyo_cd="09",
            distance_m=_CONFIRMED_DISTANCE_M,
            track_type="芝",
            field_size=len(_CONFIRMED_RESULTS),
            status="result",
            track_condition="良",
            weather="晴",
            grade="G2",
            race_class="先週重賞結果",
            rpci_actual=rpci_res.rpci,
            pci3_actual=rpci_res.pci3,
        )
    )
    # 親レースを先に確定させ、直後の race_entries 登録で FK 違反にならないようにする。
    s.flush()

    for (
        ketto,
        horse_no,
        frame_no,
        finish_pos,
        rt_s,
        a3f_s,
        c1,
        c2,
        c3,
        c4,
        rs,
    ) in _CONFIRMED_RESULTS:
        pci = _pci(rt_s, a3f_s, _CONFIRMED_DISTANCE_M)
        s.merge(
            RaceEntryModel(
                race_key=CONFIRMED_RACE_KEY,
                horse_no=horse_no,
                frame_no=frame_no,
                ketto_num=ketto,
                weight=460.0,
                jockey_code=f"JKY10{((horse_no - 1) % 4) + 1}",
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
    print(f"【今週特別登録】  {UPCOMING_RACE_KEY}  阪神11R 芝2200m 10頭")
    styles = ["逃げ", "先行", "差し", "追込", "差し", "先行", "先行", "差し", "逃げ", "追込"]
    for i, (ketto, name, _, _, _) in enumerate(_UPCOMING_HORSES):
        print(f"  {i+1:2}. {name}（{styles[i]}）  {ketto}")
    print()
    print(f"【先週結果】  {CONFIRMED_RACE_KEY}  阪神11R 芝2200m 8頭")
    print(f"  RPCI={rpci}  PCI3={pci3}")
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
