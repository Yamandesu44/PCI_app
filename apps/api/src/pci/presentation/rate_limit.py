"""公開参照APIのレート制限。

**プロセス内のみで数える。** 複数インスタンスへ広げると、実効的な上限は
インスタンス数倍になる。厳密な総量制御が要るようになったら共有ストア
（Redis 等）へ移すこと。MVP の目的は無制限スクレイピングを防ぐことなので、
インスタンス数倍でも十分に効く（CLAUDE.md「生データ再配布は禁止前提」）。
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """クライアントごとに、直近 window 秒の許可回数を制限する。

    固定窓ではなく滑動窓にしてある。固定窓は境界をまたぐと短時間に上限の2倍を
    通してしまうため、上限の意味が曖昧になる。
    """

    def __init__(
        self, limit: int, window_seconds: float = 60.0, prune_threshold: int = 4096
    ) -> None:
        if limit < 0:
            raise ValueError("limit は 0 以上でなければなりません")
        if window_seconds <= 0:
            raise ValueError("window_seconds は正でなければなりません")
        self._limit = limit
        self._window = window_seconds
        self._prune_threshold = prune_threshold
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)

    @property
    def limit(self) -> int:
        return self._limit

    def retry_after(self, key: str, now: float | None = None) -> float | None:
        """1回分を消費する。超過していれば待つべき秒数を返し、消費しない。

        戻り値が None なら許可。
        """
        if self._limit == 0:  # 0 は無効化。
            return None
        moment = time.monotonic() if now is None else now
        hits = self._hits[key]

        cutoff = moment - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= self._limit:
            # 最も古い記録が窓から外れるまで待てば1回空く。
            return max(0.0, hits[0] + self._window - moment)

        hits.append(moment)
        # 掃除は毎回やらない。キー数に比例するため、リクエストごとに走らせると
        # 相手が増えるほど1件あたりのコストが上がる。閾値を超えたときだけ行う。
        if len(self._hits) > self._prune_threshold:
            self.prune(moment)
        return None

    def prune(self, now: float | None = None) -> None:
        """窓から完全に外れたクライアントを捨てる。

        呼ばないと、一度きりの相手の分だけメモリが増え続ける。
        """
        moment = time.monotonic() if now is None else now
        cutoff = moment - self._window
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]


def client_key(direct_ip: str | None, forwarded_for: str | None, trusted_proxies: int) -> str:
    """レート制限のキーにするクライアント識別子を決める。

    PaaS のロードバランサ配下では、接続元IPは常にプロキシのものになる。そのまま
    使うと全利用者が同じキーへ集約され、制限が事実上「全体で N 回」になってしまう。

    かといって `X-Forwarded-For` を無条件に信じると、ヘッダを詐称するだけで
    制限を回避できる。**信頼できるプロキシの段数を明示した場合だけ**、右から
    その段数分を読み飛ばした値を使う。段数が 0 なら接続元IPをそのまま使う。
    """
    if trusted_proxies <= 0 or not forwarded_for:
        return direct_ip or "unknown"
    chain = [part.strip() for part in forwarded_for.split(",") if part.strip()]
    if not chain:
        return direct_ip or "unknown"
    # 右端から trusted_proxies 段はプロキシ自身。その手前が実クライアント。
    index = len(chain) - trusted_proxies
    if index < 0:
        # 申告された段数より鎖が短い＝想定と違う経路。詐称の可能性があるため
        # 接続元IPへ退避する（緩い方へ倒さない）。
        return direct_ip or "unknown"
    return chain[index - 1] if index > 0 else chain[0]
