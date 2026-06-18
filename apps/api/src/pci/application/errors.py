"""アプリケーション層の例外。

presentation 層はこれらを HTTP ステータスにマップする（統一エラーハンドラ・設計書 04 §3）。
ドメイン層には漏らさない（domain は HTTP を知らない）。
"""

from __future__ import annotations


class RaceNotConfirmedError(Exception):
    """確定前（出馬表段階）のレースに確定後分析を要求した場合に送出する（→ 409）。"""
