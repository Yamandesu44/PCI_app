"""枠順確定状態に応じて、馬の番号を誤解のない日本語へ変換する。"""

from __future__ import annotations


def horse_number_label(horse_no: int, *, confirmed: bool) -> str:
    """確定後は馬番、未確定時は登録順として1頭を表す。"""
    if confirmed:
        return f"{horse_no}番"
    return f"登録順 {horse_no}（馬番未確定）"


def horse_number_list_label(horse_numbers: tuple[int, ...], *, confirmed: bool) -> str:
    """複数頭を枠順確定状態に応じた簡潔な表記へ変換する。"""
    joined = "・".join(str(horse_no) for horse_no in horse_numbers)
    if confirmed:
        return "・".join(f"{horse_no}番" for horse_no in horse_numbers)
    return f"登録順 {joined}（馬番未確定）"
