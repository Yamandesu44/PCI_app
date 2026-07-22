"""展開コメント生成モジュール（AIコメントのMVP・ADR-0005の戦略IFに準拠）。

想定ペースや展開適性の専門指標を、PCI を知らない競馬ファンでも読み解ける
自然文の「解説」へ翻訳する。本プロダクトのコアバリュー
「PCI を理解していない競馬ファンでも展開予想を活用できる」を担う最終出力のひとつ。

MVP は決定論的なルールベース実装 `RuleBasedCommentGenerator`（comment-v2）を既定とし、
将来の LLM 実装は同一の `CommentGenerator` インターフェースを満たすことで、
application 層を無変更のまま差し替えられる（ADR-0005 の RPCI 予測と同じ疎結合方針）。

外部依存ゼロ（標準ライブラリのみ）。生成根拠は必ず reasons に出力する（説明可能性）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pci.domain.pace.horse_number_label import horse_number_label
from pci.domain.pace.rpci_forecast import PaceLabel
from pci.domain.shared.reason import Reason

COMMENTARY_VERSION = "comment-v2"


@dataclass(frozen=True)
class Commentary:
    """自然文の展開解説（UI 表示用）。headline が要点、body が段落本文。"""

    headline: str
    body: tuple[str, ...]
    model_version: str
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class BeneficiaryRef:
    """展開が向く馬の参照（馬番と PAI）。"""

    horse_no: int
    pai: float


@dataclass(frozen=True)
class ForecastCommentInput:
    """展開予想コメントの入力（出走前）。"""

    distance_m: int
    track_type: str
    field_size: int
    pace_label: PaceLabel
    predicted_rpci: float
    confidence: float
    front_runners: tuple[int, ...]
    beneficiaries: tuple[BeneficiaryRef, ...]
    horse_numbers_confirmed: bool


@dataclass(frozen=True)
class ReviewHorseRef:
    """確定後コメント用の馬参照（着順・脚質・PCI）。"""

    horse_no: int
    finish_pos: int | None
    running_style: str | None
    pci: float | None


@dataclass(frozen=True)
class ReviewCommentInput:
    """確定後ペース回顧コメントの入力。

    predicted_rpci/predicted_label は出走前に保存された想定RPCI（mart層
    predicted_pace）。actual_label は実績RPCIに classify_pace を適用した
    ラベル（呼び出し側で track_type を踏まえて計算する）。
    predicted_label が None の場合は従来通り実績のみの回顧文になる（後方互換）。
    """

    rpci_actual: float | None
    pci3_actual: float | None
    formula_version: str
    field_size: int
    sample_size: int
    horses: tuple[ReviewHorseRef, ...]
    predicted_rpci: float | None = None
    predicted_label: PaceLabel | None = None
    actual_label: PaceLabel | None = None


class CommentGenerator(Protocol):
    """展開コメント生成の戦略インターフェース（ADR-0005）。

    application / presentation 層はこの Protocol にのみ依存し、
    具体実装（ルールベース / LLM）は DI で注入する。
    """

    def forecast_comment(self, data: ForecastCommentInput) -> Commentary: ...

    def review_comment(self, data: ReviewCommentInput) -> Commentary: ...


# ----- ルールベース実装（comment-v2） -----

# 展開ラベルごとの「結論」見出し。初心者向け表示では指標名・実数値を出さない。
_FORECAST_HEADLINE: dict[PaceLabel, str] = {
    PaceLabel.HIGH: "やや速い流れになりそうです。",
    PaceLabel.AVERAGE: "極端な流れにはならず、実力どおりに決まりやすい展開とみています。",
    PaceLabel.SLOW: "やや落ち着いた流れになりそうです。",
}

# 展開ラベルごとの「なぜそうなると何が起きるか」を平易に説明する一文。
_FORECAST_CONSEQUENCE: dict[PaceLabel, str] = {
    PaceLabel.HIGH: (
        "前半から流れると、前で運ぶ馬は最後に苦しくなりやすく、"
        "後ろで脚をためる馬に出番が回ってきます。"
    ),
    PaceLabel.AVERAGE: (
        "平均的な流れなら大きな有利・不利は出にくく、"
        "普段どおり力を出せる馬を重視したいレースです。"
    ),
    PaceLabel.SLOW: (
        "前半が落ち着くと後ろから一気に届かせるのは難しく、"
        "前めで運べる馬が粘り込みやすくなります。"
    ),
}

# 想定ラベルを非専門家向けの言葉に変換する。
_PACE_WORD: dict[PaceLabel, str] = {
    PaceLabel.HIGH: "やや速い流れ",
    PaceLabel.AVERAGE: "平均的な流れ",
    PaceLabel.SLOW: "やや落ち着いた流れ",
}

_BETTING_HINT: dict[PaceLabel, str] = {
    PaceLabel.HIGH: (
        "馬券では、最後まで脚を使える馬や、少し後ろから運べる馬を相手に入れておきたいです。"
    ),
    PaceLabel.AVERAGE: "馬券では、展開だけで決めつけず、近走内容やコース相性も合わせて見たいです。",
    PaceLabel.SLOW: "馬券では、前めの位置を取れそうな馬や、直線で素早く動ける馬を重視したいです。",
}


class RuleBasedCommentGenerator:
    """ルールベース展開コメント生成器（comment-v2・テンプレート NLG）。

    指標を決定論的に自然文へ写像する。LLM を使わないため再現性が高く、
    生成根拠（どの指標から何を述べたか）を reasons に明示できる。
    """

    def forecast_comment(self, data: ForecastCommentInput) -> Commentary:
        headline = _FORECAST_HEADLINE[data.pace_label]
        body: list[str] = []

        front_clause = _front_clause(len(data.front_runners))
        pace_word = _PACE_WORD[data.pace_label]
        body.append(
            f"{data.field_size}頭立てで{front_clause}、全体としては{pace_word}になりそうです。"
        )
        body.append(_FORECAST_CONSEQUENCE[data.pace_label])
        body.append(
            _beneficiary_sentence(
                data.beneficiaries,
                horse_numbers_confirmed=data.horse_numbers_confirmed,
            )
        )
        body.append(_BETTING_HINT[data.pace_label])

        if data.confidence < 0.5:
            body.append(
                "ただし展開の確信度は高くなく、逆の流れになる可能性も頭に入れておきたいところです。"
            )

        reasons = (
            Reason(
                code="comment_basis",
                description=(
                    f"想定RPCI {data.predicted_rpci}（{data.pace_label}）・"
                    f"展開合致 {len(data.beneficiaries)}頭・確信度 {data.confidence:.0%} を要約"
                ),
            ),
            Reason(
                code="comment_model",
                description=f"ルールベース生成（{COMMENTARY_VERSION}・テンプレートNLG）",
            ),
        )
        return Commentary(
            headline=headline,
            body=tuple(body),
            model_version=COMMENTARY_VERSION,
            reasons=reasons,
        )

    def review_comment(self, data: ReviewCommentInput) -> Commentary:
        if data.rpci_actual is None:
            return Commentary(
                headline="判断材料が不足しています。",
                body=("振り返りに必要な材料が足りないため、今回は流れの評価を控えめに見てください。",),
                model_version=COMMENTARY_VERSION,
                reasons=_review_reasons(data),
            )

        pace_word, pace_clause = _actual_pace(data.rpci_actual)
        body: list[str] = []
        body.append(f"実際は{pace_clause}。")

        accuracy_sentence = _forecast_accuracy_sentence(data)
        if accuracy_sentence is not None:
            body.append(accuracy_sentence)

        winner = _winner(data.horses)
        if winner is not None and winner.pci is not None:
            style = f"（{winner.running_style}）" if winner.running_style else ""
            body.append(
                f"勝ったのは{winner.horse_no}番{style}。"
                f"{_horse_pace_phrase(winner.pci, data.rpci_actual)}。"
            )

        if data.sample_size < 3:
            body.append("完走データが少ないため、ペース評価は参考値として見てください。")

        return Commentary(
            headline=f"実際は{pace_word}でした。",
            body=tuple(body),
            model_version=COMMENTARY_VERSION,
            reasons=_review_reasons(data),
        )


def _front_clause(n_front: int) -> str:
    """先行志向の頭数を平易な句に変換する（末尾の読点は呼び出し側で付ける）。"""
    if n_front == 0:
        return "前に行きたい馬が見当たらず"
    if n_front == 1:
        return "前に行きたい馬は1頭だけで"
    return f"前に行きたい馬が{n_front}頭そろい"


def _beneficiary_sentence(
    beneficiaries: tuple[BeneficiaryRef, ...], *, horse_numbers_confirmed: bool
) -> str:
    if not beneficiaries:
        return "突出して展開が向く馬は少なく、力関係どおりに決まりそうです。"
    top = beneficiaries[0]
    top_label = horse_number_label(top.horse_no, confirmed=horse_numbers_confirmed)
    if len(beneficiaries) == 1:
        return (
            f"この流れで注目したいのは{top_label}です。"
            "展開がかみ合えば力を出しやすい一頭です。"
        )
    return (
        f"この流れで特に注目したいのが{top_label}です。"
        f"同じように流れが向きそうな馬も複数います。"
    )


def _actual_pace(rpci: float) -> tuple[str, str]:
    """確定後の流れを非専門家向けの「ペース語」と説明句に変換する（49/51 帯で3分類）。"""
    if rpci > 51.0:
        return "やや落ち着いた流れ", "前半が落ち着き、前で運んだ馬が余力を残しやすい流れでした"
    if rpci < 49.0:
        return "やや速い流れ", "前半から流れて、後ろで脚をためた馬にもチャンスが出やすい流れでした"
    return "平均的な流れ", "大きな偏りのない平均的な流れでした"


def _forecast_accuracy_sentence(data: ReviewCommentInput) -> str | None:
    """事前の想定と実績を答え合わせする一文を返す（予測データがなければ None）。"""
    if data.predicted_label is None or data.actual_label is None:
        return None
    predicted_word = _PACE_WORD[data.predicted_label]
    if data.predicted_label == data.actual_label:
        return f"事前の想定「{predicted_word}」が的中しました。"
    actual_word = _PACE_WORD[data.actual_label]
    return f"事前の想定は「{predicted_word}」でしたが、実際は「{actual_word}」という結果でした。"


def _winner(horses: tuple[ReviewHorseRef, ...]) -> ReviewHorseRef | None:
    confirmed = [h for h in horses if h.finish_pos is not None]
    if not confirmed:
        return None
    return min(confirmed, key=lambda h: h.finish_pos if h.finish_pos is not None else 9999)


def _horse_pace_phrase(horse_pci: float, rpci: float) -> str:
    """勝ち馬の指標とレース全体の流れの差から、脚の使い方を一言で表す。"""
    if horse_pci >= rpci + 2.0:
        return "後半に脚を伸ばす形で抜け出しました"
    if horse_pci <= rpci - 2.0:
        return "前々で流れに乗って押し切りました"
    return "レースの流れにうまく対応しました"


def _review_reasons(data: ReviewCommentInput) -> tuple[Reason, ...]:
    rpci = data.rpci_actual if data.rpci_actual is not None else "—"
    pci3 = data.pci3_actual if data.pci3_actual is not None else "—"
    reasons_list = [
        Reason(
            code="comment_basis",
            description=(
                f"実績RPCI {rpci}・PCI3 {pci3}・対象{data.sample_size}頭"
                f"（{data.formula_version}）を要約"
            ),
        ),
    ]
    if data.predicted_rpci is not None and data.predicted_label is not None:
        hit = data.predicted_label == data.actual_label
        reasons_list.append(
            Reason(
                code="forecast_accuracy",
                description=(
                    f"想定RPCI {data.predicted_rpci}（{data.predicted_label}）vs "
                    f"実績RPCI {rpci}（{data.actual_label}）→ "
                    f"{'的中' if hit else '外れ'}"
                ),
            )
        )
    reasons_list.append(
        Reason(
            code="comment_model",
            description=f"ルールベース生成（{COMMENTARY_VERSION}）",
        ),
    )
    return tuple(reasons_list)
