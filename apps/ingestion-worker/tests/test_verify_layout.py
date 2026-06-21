"""verify_layout / jv_spec のユニットテスト（JV-Link 不要・Linux 実行可）。

ポイント: テスト用レコードを **バイト空間** で組み立てる。spaces で埋めた
bytearray の各バイトオフセットに cp932 でフィールドを書き込むことで、
仕様書と同じ「バイト位置」のレコードを合成する（char 位置ではない）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.parser.jv_spec import (  # noqa: E402
    RA_RECORD_BYTES,
    SE_RECORD_BYTES,
    Confidence,
    get_layout,
)
from ingestion.parser.verify_layout import (  # noqa: E402
    FieldView,
    LayoutReport,
    format_report,
    verify,
)


def _place(buf: bytearray, offset: int, text: str) -> None:
    """buf の byte offset に text の cp932 バイト列を書き込む。"""
    encoded = text.encode("cp932")
    buf[offset : offset + len(encoded)] = encoded


def _build_ra(total: int = RA_RECORD_BYTES) -> str:
    """バイト正確な RA レコードを合成して str（cp932 デコード）で返す。"""
    buf = bytearray(b" " * total)
    _place(buf, 0, "RA")
    _place(buf, 2, "1")
    _place(buf, 3, "20260618")          # MakeDate
    _place(buf, 11, "2026")             # Year
    _place(buf, 15, "0618")             # MonthDay
    _place(buf, 19, "05")               # JyoCD
    _place(buf, 21, "01")               # Kaiji
    _place(buf, 23, "02")               # Nichiji
    _place(buf, 25, "11")               # RaceNum
    _place(buf, 27, "06")               # YoubiCD
    _place(buf, 29, "0000")             # TokuNum
    _place(buf, 33, "サンプルステークス")   # Hondai（全角9字=18byte）
    _place(buf, 697, "1600")            # Kyori
    _place(buf, 819, "16")              # SyussoTosu
    _place(buf, 823, "1")               # TenkoCD（晴）
    return buf.decode("cp932")


def _build_se(total: int = SE_RECORD_BYTES) -> str:
    """バイト正確な SE 確定後レコードを合成して str で返す。"""
    buf = bytearray(b" " * total)
    _place(buf, 0, "SE")
    _place(buf, 2, "4")                 # DataKubun=確定
    _place(buf, 3, "20260618")          # MakeDate
    _place(buf, 11, "2026")
    _place(buf, 15, "0618")
    _place(buf, 19, "05")
    _place(buf, 21, "01")
    _place(buf, 23, "02")
    _place(buf, 25, "11")
    _place(buf, 27, "3")                # Wakuban
    _place(buf, 28, "05")               # Umaban
    _place(buf, 30, "2023100001")       # KettoNum
    _place(buf, 40, "サンプルホース")      # Bamei（全角7字=14byte, 36byte 枠内）
    _place(buf, 78, "2")                # SexCD=牝
    _place(buf, 274, "01")              # KakuteiJyuni
    _place(buf, 330, "339")             # HaronTimeL3
    return buf.decode("cp932")


def _field(report: LayoutReport, name: str) -> FieldView:
    return next(v for v in report.fields if v.spec.name == name)


class TestLayoutTables:
    def test_ra_layout_lookup(self) -> None:
        fields, expected = get_layout("RA")
        assert expected == RA_RECORD_BYTES
        assert fields[0].name == "RecordSpec"

    def test_se_layout_lookup(self) -> None:
        fields, expected = get_layout("SE")
        assert expected == SE_RECORD_BYTES

    def test_unknown_spec_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="未対応のレコード種別"):
            get_layout("ZZ")

    def test_offsets_are_non_overlapping_and_ordered(self) -> None:
        # 全フィールドが offset 昇順で、前フィールドの end を侵食しないこと。
        for spec_id in ("RA", "SE"):
            fields, _ = get_layout(spec_id)
            prev_end = 0
            for f in fields:
                assert f.offset >= prev_end, f"{spec_id}:{f.name} が前フィールドと重複"
                assert f.length > 0
                prev_end = f.end

    def test_bamei_is_36_bytes_not_18(self) -> None:
        # char/byte の罠の核心: 馬名は byte 空間で 36（全角18字）。
        fields, _ = get_layout("SE")
        bamei = next(f for f in fields if f.name == "Bamei")
        assert bamei.length == 36
        assert bamei.confidence is Confidence.CONFIRMED


class TestVerifyRa:
    def test_anchors_all_ok(self) -> None:
        report = verify(_build_ra())
        assert report.record_spec == "RA"
        assert report.byte_length == RA_RECORD_BYTES
        assert report.all_anchors_ok, [a for a in report.anchors if not a.ok]

    def test_hondai_sliced_in_byte_space(self) -> None:
        # byte 697 に距離を置いても、byte 33 の Hondai が正しく取れる
        # （char で切っていたら Hondai 以降は全部ズレるはずの位置関係）。
        report = verify(_build_ra())
        assert _field(report, "Hondai").value == "サンプルステークス"
        assert _field(report, "Kyori").value == "1600"
        assert _field(report, "SyussoTosu").value == "16"

    def test_tenko_interpretation(self) -> None:
        report = verify(_build_ra())
        assert _field(report, "TenkoCD").interpretation == "晴"

    def test_tokunum_is_zero_for_general_race(self) -> None:
        report = verify(_build_ra())
        assert _field(report, "TokuNum").value == "0000"


class TestVerifySe:
    def test_anchors_all_ok(self) -> None:
        report = verify(_build_se())
        assert report.record_spec == "SE"
        assert report.byte_length == SE_RECORD_BYTES
        assert report.all_anchors_ok, [a for a in report.anchors if not a.ok]

    def test_bamei_and_downstream_sliced_in_byte_space(self) -> None:
        report = verify(_build_se())
        assert _field(report, "Bamei").value == "サンプルホース"
        # 確定着順は byte 274（旧 char parser の 580 ではない）。
        assert _field(report, "KakuteiJyuni").value == "01"
        assert _field(report, "HaronTimeL3").value == "339"

    def test_sex_interpretation(self) -> None:
        report = verify(_build_se())
        assert _field(report, "SexCD").value == "2"
        assert _field(report, "SexCD").interpretation == "牝"

    def test_data_kubun_anchor_decoded(self) -> None:
        report = verify(_build_se())
        dk = next(a for a in report.anchors if a.name == "DataKubun")
        assert dk.ok
        assert "確定" in dk.detail


class TestAnchorFailures:
    def test_short_record_flags_length(self) -> None:
        # 旧 char 長 (~244) のような短いレコードは長さアンカーが NG。
        report = verify(_build_se(total=SE_RECORD_BYTES)[:200])
        length_anchor = next(a for a in report.anchors if a.name == "レコード長")
        assert not length_anchor.ok
        assert not report.all_anchors_ok

    def test_trailing_padding_is_tolerated(self) -> None:
        # JVRead のバッファ余白で末尾に空白が付いても先頭側は使える。
        report = verify(_build_ra() + "   ")
        length_anchor = next(a for a in report.anchors if a.name == "レコード長")
        assert length_anchor.ok


class TestFormatReport:
    def test_report_renders_key_sections(self) -> None:
        text = format_report(verify(_build_ra()))
        assert "アンカー検証" in text
        assert "フィールド一覧" in text
        assert "Hondai" in text
        # TENTATIVE フィールドには注記行が付く。
        assert "↳" in text
