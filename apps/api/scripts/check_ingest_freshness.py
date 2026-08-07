"""公開中のAPIへ問い合わせ、取り込みが止まっていないかを確認する。

取り込みが止まっても**画面は壊れない。古いままになるだけ**で、見た目は正常に動く。
公開後に最も気付きにくい壊れ方なので、外から定期的に確かめる。

判定は `/api/v1/ingest-status` の結果に従う。異常なら終了コード1で落ちる。
GitHub Actions の定期実行から呼ぶと、失敗時に通知が届く（.github/workflows/monitor-ingest.yml）。

標準ライブラリだけで動く。依存を入れずに実行できるようにするためで、
`pci` パッケージは import しない（監視のために本体を入れるのは重い）。

使い方:
    python scripts/check_ingest_freshness.py --base-url https://... --token "$PUBLIC_API_TOKEN"
    python scripts/check_ingest_freshness.py --base-url ... --token ... --max-days 4
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any

# JRA は金土日の周期で開催する。取り込みもその周期に合わせてあるため、
# 4日空くのは通常の運用では起こらない。開催の無い週があっても、
# 特別登録の取り込みが動くので更新自体は途切れない。
_DEFAULT_MAX_DAYS = 4

_TIMEOUT_SECONDS = 60.0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", required=True, help="公開中のAPIのURL")
    p.add_argument("--token", default=None, help="PUBLIC_API_TOKEN。設定済みなら必須。")
    p.add_argument(
        "--max-days",
        type=int,
        default=_DEFAULT_MAX_DAYS,
        help=f"最終成功からの許容日数（既定{_DEFAULT_MAX_DAYS}）。",
    )
    return p.parse_args()


def _fetch(base_url: str, token: str | None) -> dict[str, Any]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/api/v1/ingest-status")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    # Cloud Run はゼロスケールするため、最初の1本はコールドスタートを含む。
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        body: dict[str, Any] = json.loads(response.read())
        return body


def main() -> None:
    args = _parse_args()

    try:
        status = _fetch(args.base_url, args.token)
    except urllib.error.HTTPError as exc:
        # 401 はトークンの不一致。取り込みの問題と紛らわしいので分けて出す。
        hint = "PUBLIC_API_TOKEN を確認してください。" if exc.code in (401, 403) else ""
        raise SystemExit(f"✗ 取り込み状況を取得できません（HTTP {exc.code}）。{hint}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"✗ APIへ到達できません（{type(exc).__name__}）。") from exc

    last_success = status.get("last_success_at")
    days = status.get("days_since_last_success")
    failures = status.get("recent_failures") or []

    print(f"最終成功: {last_success or '記録なし'}（{days if days is not None else '?'} 日前）")
    print(f"直近の失敗: {len(failures)} 件")

    problems: list[str] = []

    if not status.get("has_history"):
        # 本番で履歴が無いのは、取り込みが一度も届いていないということ。
        problems.append("取り込みの履歴がありません。ワーカーがAPIへ届いていない可能性があります。")

    if status.get("last_attempt_failed"):
        problems.append("直近の取り込みが失敗しています。")

    if status.get("is_stale"):
        problems.append("APIが鮮度不足と判定しています。")

    if days is not None and days > args.max_days:
        problems.append(f"最終成功から {days} 日経過しています（許容 {args.max_days} 日）。")

    for failure in failures[:5]:
        # 時刻も出す。「古い記録が残っているだけ」か「今また失敗した」かは、
        # これが無いと区別できない。
        print(
            f"  - {failure.get('started_at', '?')} {failure.get('step', '?')}: "
            f"{failure.get('error_summary', '')[:160]}"
        )

    if problems:
        print()
        for problem in problems:
            print(f"✗ {problem}")
        print(
            "\nWindows機のタスクスケジューラ（PaceLab_Sync_Mykeibadb）の実行結果を確認してください。"
        )
        raise SystemExit(1)

    print("\n✓ 取り込みは動いています。")


if __name__ == "__main__":
    main()
