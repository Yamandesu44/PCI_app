"""diagnose_results（確定成績の切り分け診断）のユニットテスト（実DB不要）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_mykeibadb_client import _Connection  # noqa: E402

from ingestion.client.mykeibadb_client import MyKeibaDbClient  # noqa: E402
from ingestion.diagnose_results import diagnose  # noqa: E402


class _NoResultConnection(_Connection):
    """SE 行はあるが着順・タイム・上り3F が全て欠落した mykeibadb を模す。

    「mykeibadb に確定成績が未取得」または「結果列名が候補と不一致」のケース。
    """

    se = [
        {
            "開催年月日": "20260719",
            "競馬場コード": "09",
            "開催回": "01",
            "開催日次": "03",
            "レース番号": "11",
            "枠番": "1",
            "馬番": "1",
            "血統登録番号": "2021100001",
            "馬名": "テストホース",
            "性別": "牡",
            "調教師コード": "01001",
            "騎手コード": "02001",
            # 着順・タイム・上り3F 列そのものが無い（＝確定データ未取得を模す）
        }
    ]


def test_diagnose_reports_confirmed_results(capsys: pytest.CaptureFixture[str]) -> None:
    """結果3項目が揃った SE 行では parse 成功件数を報告し「正常」判定する。"""
    client = MyKeibaDbClient(connection=_Connection())

    diagnose("20260620", "20260622", show_values=False, sample_limit=3, client=client)

    out = capsys.readouterr().out
    assert "parse_se_result 成功: 1" in out
    # RA も揃っているので、原因は解析ではなく「送信」段階だと案内する分岐に入る。
    assert "対応する RA も揃っている" in out
    assert "確定成績はあるが RA が無いレース数: 0" in out


def test_diagnose_flags_missing_result_columns(capsys: pytest.CaptureFixture[str]) -> None:
    """結果列が欠落した SE 行では『0件』を集計し、原因候補を提示する。"""
    client = MyKeibaDbClient(connection=_NoResultConnection())

    diagnose("20260718", "20260720", show_values=False, sample_limit=3, client=client)

    out = capsys.readouterr().out
    assert "SE 行数: 1" in out
    assert "3項目すべてあり: 0" in out
    assert "parse_se_result 成功: 0" in out
    # 判定セクションが (A)/(B) の切り分けを促していること
    assert "列名" in out


class _NoRaConnection(_Connection):
    """SE の確定成績はあるが、対応する RA（出走表元）が無い mykeibadb を模す。

    取り込みは RA からレースを作るため、RA が無いと record_results が
    「レースが見つかりません」で失敗する。診断はこれを検出できる必要がある。
    """

    ra: list[dict[str, Any]] = []


def test_diagnose_flags_results_without_ra(capsys: pytest.CaptureFixture[str]) -> None:
    """確定成績はあるが RA が無い場合、レース未登録による送信失敗の可能性を提示する。"""
    client = MyKeibaDbClient(connection=_NoRaConnection())

    diagnose("20260620", "20260622", show_values=False, sample_limit=3, client=client)

    out = capsys.readouterr().out
    assert "parse_se_result 成功: 1" in out
    assert "確定成績はあるが RA が無いレース数: 1" in out
    assert "レースが見つかりません" in out


def test_diagnose_reports_empty_period(capsys: pytest.CaptureFixture[str]) -> None:
    """対象期間に SE 行が無ければ mykeibadb 未取得の可能性を明示する。"""
    client = MyKeibaDbClient(connection=_Connection())

    # _Connection.se は 20260621 のみ。範囲外を指定すると0件になる。
    diagnose("20260101", "20260102", show_values=False, sample_limit=3, client=client)

    out = capsys.readouterr().out
    assert "SE 行数: 0" in out
    assert "未取得" in out
