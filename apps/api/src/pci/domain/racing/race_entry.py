from __future__ import annotations

from dataclasses import dataclass, field

from pci.domain.shared.race_key import RaceKey


@dataclass
class RaceEntry:
    """出走馬ごとのエントリ。確定後は成績フィールドが埋まる（ADR-0006）。"""

    race_key: RaceKey
    horse_no: int
    frame_no: int
    ketto_num: str  # 血統登録番号
    weight: float  # 馬体重(kg)。既存DB/API名との互換性のためフィールド名は維持。
    jockey_code: str
    trainer_code: str

    # 確定後（すべて nullable）
    finish_pos: int | None = field(default=None)
    race_time_s: float | None = field(default=None)  # 走破タイム(秒)
    agari_3f_s: float | None = field(default=None)  # 上がり3F(秒)
    corner_1: int | None = field(default=None)
    corner_2: int | None = field(default=None)
    corner_3: int | None = field(default=None)
    corner_4: int | None = field(default=None)  # 脚質判定に使用
    pci_actual: float | None = field(default=None)  # formula_version は mart 層で管理
    running_style: str | None = field(default=None)  # RunningStyleLabel の値
    # Phase2（能力指数 ability-v2 用・確定後）。未取得は None。
    popularity: int | None = field(default=None)  # 単勝人気順（1=1番人気）
    prize_money: int | None = field(default=None)  # 獲得本賞金（円）

    @property
    def corner4_position(self) -> int | None:
        """4角通過順位（脚質判定の入力に使用）。"""
        return self.corner_4
