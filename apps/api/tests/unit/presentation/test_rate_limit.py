"""レート制限の純粋ロジックの単体テスト。"""

from __future__ import annotations

import pytest

from pci.presentation.rate_limit import SlidingWindowRateLimiter, client_key


class TestSlidingWindowRateLimiter:
    def test_allows_up_to_the_limit(self) -> None:
        limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60.0)

        assert [limiter.retry_after("a", now=0.0) for _ in range(3)] == [None, None, None]

    def test_blocks_beyond_the_limit(self) -> None:
        limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60.0)
        limiter.retry_after("a", now=0.0)
        limiter.retry_after("a", now=0.0)

        wait = limiter.retry_after("a", now=0.0)

        assert wait == pytest.approx(60.0)

    def test_blocked_requests_do_not_consume_the_budget(self) -> None:
        """はじいた分まで数えると、待ち時間が伸び続けて復帰できなくなる。"""
        limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60.0)
        limiter.retry_after("a", now=0.0)
        limiter.retry_after("a", now=10.0)  # はじかれる

        # 最初の1回が窓から外れた直後には通る。
        assert limiter.retry_after("a", now=60.1) is None

    def test_window_slides_rather_than_resetting(self) -> None:
        """固定窓なら境界をまたいだ瞬間に上限の2倍を通してしまう。

        窓の終わり際に上限まで使った直後、固定窓は次の窓が始まったとみなして
        さらに上限分を通す（1秒ほどの間に4回）。滑動窓ではそうならない。
        """
        limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60.0)
        limiter.retry_after("a", now=59.0)
        limiter.retry_after("a", now=59.5)

        # 固定窓ならここで窓が切り替わって通る。滑動窓では2回とも窓内なので通らない。
        assert limiter.retry_after("a", now=60.1) is not None

        # 59.0 の分が窓から外れて初めて1回空く。
        assert limiter.retry_after("a", now=119.1) is None
        # 59.5 の分はまだ窓内なので、続けてもう1回は通らない。
        assert limiter.retry_after("a", now=119.2) is not None

    def test_clients_are_counted_separately(self) -> None:
        limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60.0)
        limiter.retry_after("a", now=0.0)

        assert limiter.retry_after("b", now=0.0) is None

    def test_zero_limit_disables_the_check(self) -> None:
        limiter = SlidingWindowRateLimiter(limit=0, window_seconds=60.0)

        assert all(limiter.retry_after("a", now=0.0) is None for _ in range(100))

    def test_rejects_invalid_settings(self) -> None:
        with pytest.raises(ValueError, match="limit"):
            SlidingWindowRateLimiter(limit=-1)
        with pytest.raises(ValueError, match="window_seconds"):
            SlidingWindowRateLimiter(limit=1, window_seconds=0.0)

    def test_prune_drops_idle_clients(self) -> None:
        """掃除しないと、一度きりの相手の分だけメモリが増え続ける。"""
        limiter = SlidingWindowRateLimiter(limit=5, window_seconds=60.0)
        for i in range(50):
            limiter.retry_after(f"client-{i}", now=0.0)

        limiter.prune(now=120.0)

        # 掃除後も新しい相手は通常どおり通る。
        assert limiter.retry_after("client-0", now=120.0) is None

    def test_prunes_automatically_past_the_threshold(self) -> None:
        limiter = SlidingWindowRateLimiter(limit=5, window_seconds=60.0, prune_threshold=10)
        for i in range(20):
            limiter.retry_after(f"old-{i}", now=0.0)

        # 窓の外から新規に叩くと、その時点で古い分が落ちる。
        limiter.retry_after("new", now=1000.0)

        assert limiter.retry_after("old-0", now=1000.0) is None


class TestClientKey:
    def test_uses_the_socket_ip_without_trusted_proxies(self) -> None:
        assert client_key("203.0.113.9", "198.51.100.1", trusted_proxies=0) == "203.0.113.9"

    def test_ignores_a_forged_header_when_no_proxy_is_declared(self) -> None:
        """段数を宣言していなければヘッダは信じない。信じると詐称で回避できる。"""
        assert client_key("203.0.113.9", "1.1.1.1, 2.2.2.2", trusted_proxies=0) == "203.0.113.9"

    def test_reads_past_one_trusted_proxy(self) -> None:
        assert client_key("10.0.0.1", "198.51.100.7, 10.0.0.1", trusted_proxies=1) == "198.51.100.7"

    def test_reads_past_two_trusted_proxies(self) -> None:
        chain = "198.51.100.7, 10.0.0.9, 10.0.0.1"
        assert client_key("10.0.0.1", chain, trusted_proxies=2) == "198.51.100.7"

    def test_falls_back_when_the_chain_is_shorter_than_declared(self) -> None:
        """申告より鎖が短い＝想定と違う経路。緩い方へ倒さず接続元IPを使う。"""
        assert client_key("10.0.0.1", "198.51.100.7", trusted_proxies=3) == "10.0.0.1"

    def test_handles_a_missing_header(self) -> None:
        assert client_key("10.0.0.1", None, trusted_proxies=1) == "10.0.0.1"

    def test_handles_a_missing_socket_ip(self) -> None:
        assert client_key(None, None, trusted_proxies=0) == "unknown"
