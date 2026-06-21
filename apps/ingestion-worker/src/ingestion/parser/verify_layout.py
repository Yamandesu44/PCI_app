"""実 JV-Data レコードを仕様マップ（jv_spec）と突き合わせて検証するハーネス。

Windows での使い方（どちらでも可）::

    # 直接実行 — PYTHONPATH 不要（このファイルを src 配下から参照）
    cd C:\\path\\to\\PCI_app\\apps\\ingestion-worker
    py -3.12-32 src\\ingestion\\parser\\verify_layout.py dumped_ra.txt

    # -m 実行 — 先に PYTHONPATH を設定する
    cd C:\\path\\to\\PCI_app\\apps\\ingestion-worker
    set PYTHONPATH=%CD%\\src
    py -3.12-32 -m ingestion.parser.verify_layout dumped_ra.txt

ファイルの代わりに標準入力も使える::

    type dumped_ra.txt | py -3.12-32 src\\ingestion\\parser\\verify_layout.py

設計意図:
  JV-Data のオフセットは全て **バイト** 単位。``record.encode("cp932")`` した bytes 上で
  jv_spec のオフセットを適用するため、全角フィールドを跨いでもズレない。
  「アンカー検証」でヘッダ（種別ID・作成日・開催年月日）の整合を先に確かめてから、
  TENTATIVE フィールドの値を目視で確定していく運用を想定する。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# 直接スクリプト実行（py verify_layout.py）時でも import ingestion.* が解決できるよう
# このファイルの 3 階層上の src ディレクトリを sys.path に追加する。
# -m 実行時はすでに解決済みなので二重登録になるだけで無害。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingestion.parser.common import decode_baba, decode_sex, decode_tenko  # noqa: E402
from ingestion.parser.jv_spec import Confidence, FieldSpec, get_layout  # noqa: E402

_DATA_KUBUN: dict[str, str] = {
    "0": "削除",
    "1": "新規",
    "2": "更新",
    "3": "取消/除外",
    "4": "確定",
    "5": "成績確定",
    "7": "確定",  # RA・SE ともに実測確認: 2026-06-13 函館1R
    "9": "レース中止",
}

_MAX_VALUE_DISPLAY = 48


@dataclass(frozen=True)
class AnchorResult:
    """ヘッダ整合性チェック 1 件の結果。"""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class FieldView:
    """1 フィールドのスライス結果。"""

    spec: FieldSpec
    raw_value: str           # cp932 デコード後（トリム前）
    value: str               # 表示用トリム済み
    interpretation: str | None
    in_range: bool


@dataclass(frozen=True)
class LayoutReport:
    """1 レコードの検証結果。"""

    record_spec: str
    byte_length: int
    expected_length: int
    anchors: tuple[AnchorResult, ...]
    fields: tuple[FieldView, ...]

    @property
    def all_anchors_ok(self) -> bool:
        return all(a.ok for a in self.anchors)


def to_cp932(record: str) -> bytes:
    """JV-Link が返す Unicode 文字列を元の CP932(Shift-JIS) バイト列に戻す。"""
    return record.encode("cp932", errors="replace")


def _interpret(field: FieldSpec, value: str) -> str | None:
    """コードフィールドの意味を補助表示する（確認しやすさのため）。"""
    if field.name == "SexCD":
        return decode_sex(value)
    if field.name == "TenkoCD":
        return decode_tenko(value)
    if field.name in ("SibaBabaCD", "DirtBabaCD"):
        return decode_baba(value)
    if field.name == "DataKubun":
        return _DATA_KUBUN.get(value)
    return None


def _build_views(raw: bytes, fields: tuple[FieldSpec, ...]) -> tuple[FieldView, ...]:
    views: list[FieldView] = []
    for field in fields:
        if len(raw) < field.end:
            views.append(FieldView(field, "", "(範囲外)", None, False))
            continue
        decoded = raw[field.offset : field.end].decode("cp932", errors="replace")
        trimmed = decoded.strip()
        views.append(FieldView(field, decoded, trimmed, _interpret(field, trimmed), True))
    return tuple(views)


def _check_anchors(raw: bytes, spec_id: str, expected_len: int) -> tuple[AnchorResult, ...]:
    results: list[AnchorResult] = []
    n = len(raw)

    if n == expected_len:
        results.append(AnchorResult("レコード長", True, f"{n} byte = 仕様データ長 {expected_len}"))
    elif n > expected_len:
        results.append(
            AnchorResult(
                "レコード長",
                True,
                f"{n} byte（仕様 {expected_len} + 余白 {n - expected_len}。先頭側を使用）",
            )
        )
    else:
        results.append(
            AnchorResult(
                "レコード長",
                False,
                f"{n} byte < 仕様 {expected_len}。CR/LF 除去や encode 前処理を確認",
            )
        )

    rec_spec = raw[0:2].decode("cp932", errors="replace")
    results.append(
        AnchorResult("RecordSpec", rec_spec == spec_id, f"{rec_spec!r}（期待 {spec_id!r}）")
    )

    data_kubun = raw[2:3].decode("cp932", errors="replace")
    dk_meaning = _DATA_KUBUN.get(data_kubun, "?")
    results.append(
        AnchorResult("DataKubun", data_kubun.isdigit(), f"{data_kubun!r}（{dk_meaning}）")
    )

    make_date = raw[3:11].decode("cp932", errors="replace")
    results.append(
        AnchorResult("MakeDate", make_date.isdigit() and len(make_date) == 8, f"{make_date!r}")
    )

    year = raw[11:15].decode("cp932", errors="replace")
    mmdd = raw[15:19].decode("cp932", errors="replace")
    year_ok = year.isdigit() and 1980 <= int(year) <= 2100
    mmdd_ok = (
        mmdd.isdigit()
        and 1 <= int(mmdd[:2]) <= 12
        and 1 <= int(mmdd[2:]) <= 31
    )
    detail = (
        f"{year}-{mmdd[:2]}-{mmdd[2:]}"
        if year.isdigit() and mmdd.isdigit()
        else f"{year!r}{mmdd!r}"
    )
    results.append(AnchorResult("開催年月日", year_ok and mmdd_ok, detail))

    return tuple(results)


def verify(record: str) -> LayoutReport:
    """1 レコード文字列を検証して LayoutReport を返す。

    先頭 2 byte をレコード種別IDとみなしてレイアウトを選ぶ。未対応種別は ValueError。
    """
    spec_id = record[:2]
    fields, expected = get_layout(spec_id)
    raw = to_cp932(record)
    anchors = _check_anchors(raw, spec_id, expected)
    views = _build_views(raw, fields)
    return LayoutReport(spec_id, len(raw), expected, anchors, views)


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_VALUE_DISPLAY else text[: _MAX_VALUE_DISPLAY - 1] + "…"


def format_report(report: LayoutReport) -> str:
    """LayoutReport を人間可読なテキストに整形する。"""
    lines: list[str] = []
    bar = "=" * 72
    lines.append(bar)
    lines.append(f" JV-Data レイアウト検証: {report.record_spec} レコード")
    lines.append(bar)
    lines.append("")
    lines.append("[アンカー検証]  （ヘッダが揃っていれば byte オフセットの起点は正しい）")
    for anchor in report.anchors:
        mark = "OK" if anchor.ok else "NG"
        lines.append(f"  {mark}  {anchor.name}: {anchor.detail}")
    lines.append("")
    lines.append("[フィールド一覧]  （✓=確度高 / ?=要実データ確認）")
    name_width = max((len(v.spec.name) for v in report.fields), default=10)
    for view in report.fields:
        field = view.spec
        conf = "✓" if field.confidence is Confidence.CONFIRMED else "?"
        display = _truncate(view.value) if view.in_range else "(範囲外)"
        interp = f"  → {view.interpretation}" if view.interpretation else ""
        lines.append(
            f"  {conf} [{field.offset:4d}:{field.end:4d}] "
            f"(len{field.length:>3}) {field.name:<{name_width}} = {display!r}{interp}"
        )
        if field.confidence is Confidence.TENTATIVE and field.note:
            lines.append(f"          ↳ {field.note}")
    lines.append("")
    return "\n".join(lines)


def format_byte_map(record: str, ruler_from: int = 82) -> str:
    """CP932 バイトの非空白マップとバイトルーラーを返す（フィールド位置特定用）。

    非空白マップ: space(0x20)/NUL(0x00) 以外の連続バイト列を列挙する。
    バイトルーラー: ruler_from 以降を 10 バイトごとに表示する。
    結果フィールドが未確定の SE 等で正しい byte オフセットを目視特定するために使う。
    """
    raw = to_cp932(record)
    n = len(raw)
    lines: list[str] = []

    lines.append(f"\n{'=' * 72}")
    lines.append(f" バイトマップ  len={n}  — フィールド位置特定用")
    lines.append(f"{'=' * 72}")

    # 非空白領域マップ（space/NUL を空白とみなす）
    blank = {0x20, 0x00}
    lines.append("[非空白領域マップ]  (space/NUL を除いた連続バイト):")
    i = 0
    while i < n:
        if raw[i] not in blank:
            j = i
            while j < n and raw[j] not in blank:
                j += 1
            decoded = raw[i:j].decode("cp932", errors="replace")
            lines.append(f"  [{i:4d}:{j:4d}] (len{j - i:3d}) {decoded!r}")
            i = j
        else:
            i += 1

    # バイトルーラー（ruler_from 以降）
    lines.append(f"\n[バイトルーラー: {ruler_from}〜{n}]  (10バイトごと):")
    for pos in range(ruler_from, n, 10):
        chunk = raw[pos : pos + 10]
        decoded = chunk.decode("cp932", errors="replace")
        lines.append(f"  [{pos:4d}:{pos + 10:4d}] {decoded!r}")

    return "\n".join(lines)


def _extract_record(text: str) -> str:
    """ファイル/標準入力のテキストから最初のレコード行を取り出す。

    コメント行（# 始まり）と空行を読み飛ばし、CR/LF を除去する。
    """
    for line in text.splitlines():
        stripped = line.rstrip("\r\n")
        if stripped and not stripped.lstrip().startswith("#"):
            return stripped
    return ""


def main(argv: list[str] | None = None) -> int:
    """エントリーポイント。

    Usage::

        verify_layout [--map] [FILE]

    --map: 仕様マップ照合に加え、CP932 バイト全域の非空白マップと
           バイトルーラーを出力する。SE 等の結果フィールドオフセットを
           特定する際に使う（出力が長くなる）。
    """
    args = sys.argv[1:] if argv is None else argv
    show_map = "--map" in args
    file_args = [a for a in args if not a.startswith("--")]
    text = Path(file_args[0]).read_text(encoding="utf-8") if file_args else sys.stdin.read()

    record = _extract_record(text)
    if not record:
        print("レコードが見つかりません（入力が空かコメントのみ）", file=sys.stderr)
        return 1

    try:
        report = verify(record)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(format_report(report))
    if show_map:
        print(format_byte_map(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
