from dataclasses import dataclass


@dataclass(frozen=True)
class Distance:
    """レース距離 (m)。PCI計算式の都合上 600m 超が必要（前半区間ゼロ除算防止）。"""

    meters: int

    def __post_init__(self) -> None:
        if not (600 < self.meters <= 4000):
            raise ValueError(f"距離は600m超〜4000m以下で入力してください: {self.meters}m")


@dataclass(frozen=True)
class RaceTime:
    """走破タイム (秒)。"""

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise ValueError(f"走破タイムは正の値でなければなりません: {self.seconds}秒")


@dataclass(frozen=True)
class Furlong3Time:
    """上がり3ハロン (600m) の走破タイム (秒)。"""

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise ValueError(f"上がり3Fは正の値でなければなりません: {self.seconds}秒")


@dataclass(frozen=True)
class CornerPositions:
    """1走における各コーナー通過順位（None = 通過なし）。"""

    c1: int | None = None
    c2: int | None = None
    c3: int | None = None
    c4: int | None = None

    def __post_init__(self) -> None:
        for name, val in (("c1", self.c1), ("c2", self.c2), ("c3", self.c3), ("c4", self.c4)):
            if val is not None and val < 1:
                raise ValueError(f"{name}通過順位は1以上でなければなりません: {val}")
