from dataclasses import dataclass


@dataclass(frozen=True)
class Reason:
    """算出結果の説明要素。説明可能性の原則（CLAUDE.md）に従い全算出結果に付与する。"""

    code: str
    description: str
    contribution: float | None = None
