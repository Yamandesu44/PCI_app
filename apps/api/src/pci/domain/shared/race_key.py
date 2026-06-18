from dataclasses import dataclass


@dataclass(frozen=True)
class RaceKey:
    """レース識別子。16桁数字: 年(4)+月日(4)+競馬場(2)+回(2)+日目(2)+R(2)。"""

    value: str

    def __post_init__(self) -> None:
        if len(self.value) != 16 or not self.value.isdigit():
            raise ValueError(f"RaceKey は16桁の数字でなければなりません: {self.value!r}")

    def __str__(self) -> str:
        return self.value
