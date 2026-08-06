"""公開したAPIが、意図した設定で動いているかを外から確認する。

デプロイの失敗は「落ちる」形では現れないことが多い。**設定が抜けたまま起動し、
一見正常に応答する**のが厄介で、次のような状態はログを見ても気付けない。

  - `PUBLIC_API_TOKEN` の入れ忘れ → 誰でも全データを読める（JRA-VAN 由来の
    データを再配布している状態になる。CLAUDE.md「生データ再配布は禁止前提」）
  - `MODELS_DIR` の解決失敗 → 例外も出さずルールベースへ落ち、精度だけ静かに下がる
  - `CORS_ALLOW_ORIGINS` の緩め過ぎ → 任意のサイトからブラウザ経由で読み出せる

これらを、デプロイ直後に**外から**確かめる。中に入らないと分からない項目
（`RATE_LIMIT_TRUSTED_PROXIES` 等）は最後に「確認できない項目」として並べる。

読み取りのみで、DBもデプロイも変更しない。

使い方:
    cd apps/api
    python -m scripts.check_deployment --base-url https://pci-api-xxxx.a.run.app \\
        --token "$PUBLIC_API_TOKEN"

    # トークン未設定の環境（手元など）を確認する場合は --token を省く
    python -m scripts.check_deployment --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Literal

import httpx

# Cloud Run はゼロスケールするため、最初の1本はコールドスタートを含む。
_FIRST_REQUEST_TIMEOUT = 60.0
_TIMEOUT = 20.0

# CORS の確認に使う、こちらの管理外であることが明らかなオリジン。
_FOREIGN_ORIGIN = "https://example.invalid"

Severity = Literal["critical", "warning", "ok"]


def _get(client: httpx.Client, path: str, **kwargs: Any) -> httpx.Response:
    """GET。切れた接続を掴んだ場合だけ1度だけ張り直す。

    直前の応答がエラーだとサーバ側が接続を閉じることがあり、使い回した接続が
    そのまま `ReadError` になる。**確認できなかっただけなのに「確認できません」と
    報告してしまう**ので、輸送層の失敗に限って新しい接続で1回やり直す。
    """
    try:
        return client.get(path, **kwargs)
    except httpx.TransportError:
        return client.get(path, **kwargs)


@dataclass(frozen=True)
class Check:
    name: str
    severity: Severity
    detail: str
    action: str | None = None


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", required=True, help="公開したAPIのURL（末尾の / は不要）")
    p.add_argument(
        "--token",
        default=None,
        help="APIの PUBLIC_API_TOKEN。省略すると、認証が無効である前提で確認する。",
    )
    return p.parse_args()


def _check_health(client: httpx.Client) -> Check:
    try:
        response = _get(client, "/health", timeout=_FIRST_REQUEST_TIMEOUT)
    except httpx.HTTPError as exc:
        return Check(
            "疎通",
            "critical",
            f"接続できません（{type(exc).__name__}）。",
            "URLと、サービスが起動しているかを確認してください。",
        )
    if response.status_code != 200:
        return Check("疎通", "critical", f"/health が {response.status_code} を返しました。")
    return Check("疎通", "ok", "/health が応答しました。")


def _check_readiness(client: httpx.Client) -> Check:
    try:
        response = _get(client, "/ready")
    except httpx.HTTPError as exc:
        return Check("DB接続", "critical", f"/ready へ到達できません（{type(exc).__name__}）。")

    body = response.json()
    if response.status_code == 200 and body.get("status") == "ready":
        return Check("DB接続", "ok", "DBへ接続でき、マイグレーションも最新です。")

    return Check(
        "DB接続",
        "critical",
        body.get("message") or f"/ready が {response.status_code} を返しました。",
        body.get("action"),
    )


def _check_public_api_protected(client: httpx.Client, token: str | None) -> list[Check]:
    """認証が効いているかを、トークン無し・有りの両方で確かめる。"""
    checks: list[Check] = []
    try:
        anonymous = _get(client, "/api/v1/races/dates")
    except httpx.HTTPError as exc:
        return [Check("認証", "critical", f"確認できません（{type(exc).__name__}）。")]

    if token is None:
        if anonymous.status_code == 200:
            checks.append(
                Check(
                    "認証",
                    "warning",
                    "トークン無しで参照できました（--token 未指定のため想定どおり）。",
                    "外部から到達できる場所では PUBLIC_API_TOKEN を設定してください。",
                )
            )
        else:
            checks.append(
                Check(
                    "認証",
                    "warning",
                    f"認証が有効です（{anonymous.status_code}）。"
                    "--token を渡すと続きを確認できます。",
                )
            )
        return checks

    if anonymous.status_code != 401:
        # 401 以外はどの番号でも「認証で止まらなかった」ことを意味する。
        # 応答が 500 でも、middleware を通り抜けて処理へ入った証拠に変わりはない。
        # 鍵を掛けたつもりで全公開になっている状態。
        checks.append(
            Check(
                "認証",
                "critical",
                f"トークン無しの参照が認証で止まりませんでした（{anonymous.status_code}）。"
                "誰でも全データを読める状態です。",
                "APIの PUBLIC_API_TOKEN が設定され、反映されているか確認してください。",
            )
        )
    else:
        checks.append(Check("認証", "ok", "トークン無しの参照は 401 で拒否されました。"))

    try:
        authorized = _get(
            client,
            "/api/v1/races/dates",
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        return [*checks, Check("トークン", "critical", f"確認できません（{type(exc).__name__}）。")]

    if authorized.status_code == 200:
        checks.append(Check("トークン", "ok", "渡したトークンで参照できました。"))
    elif authorized.status_code in (401, 403):
        checks.append(
            Check(
                "トークン",
                "critical",
                f"渡したトークンが拒否されました（{authorized.status_code}）。",
                "APIの PUBLIC_API_TOKEN と、web の API_ACCESS_TOKEN の値を突き合わせてください。",
            )
        )
    else:
        # 認証は通っている。500 等はDB側の問題で、原因は別の項目が示している。
        # ここでトークンのせいにすると、正しい値を疑わせることになる。
        checks.append(
            Check(
                "トークン",
                "warning",
                f"認証は通りましたが、応答が {authorized.status_code} でした。",
                "他の項目に出ている原因を先に解消してください。",
            )
        )
    return checks


def _check_cors(client: httpx.Client) -> Check:
    """許可オリジンの絞り込み。

    CORS は middleware なので、どの経路でも同じ判定になる。**DBを触らない
    `/health` で確かめる**——参照APIで確かめると、DBが落ちている環境では
    そちらのエラーに巻き込まれて CORS の可否そのものが分からなくなる。
    """
    try:
        response = _get(client, "/health", headers={"Origin": _FOREIGN_ORIGIN})
    except httpx.HTTPError as exc:
        return Check("CORS", "warning", f"確認できません（{type(exc).__name__}）。")

    allowed = response.headers.get("access-control-allow-origin")
    if allowed is None:
        return Check("CORS", "ok", "無関係なオリジンには許可を返しませんでした。")
    if allowed == "*" or allowed == _FOREIGN_ORIGIN:
        return Check(
            "CORS",
            "warning",
            f"任意のオリジンへ許可を返しています（{allowed}）。",
            "CORS_ALLOW_ORIGINS を公開フロントのオリジンだけに絞ってください。",
        )
    return Check("CORS", "ok", f"許可オリジンは限定されています（{allowed}）。")


def _check_forecaster(client: httpx.Client, token: str | None) -> Check:
    """予測モデルが読めているか。読めていなければ静かにルールベースへ落ちている。"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        dates = _get(client, "/api/v1/races/dates", headers=headers)
        if dates.status_code != 200 or not dates.json():
            return Check("予測モデル", "warning", "開催日が取得できず、確認できませんでした。")
        latest = dates.json()[-1]

        races = _get(client, "/api/v1/races", params={"date": latest, "limit": 1}, headers=headers)
        if races.status_code != 200 or not races.json():
            return Check("予測モデル", "warning", "レースが取得できず、確認できませんでした。")
        race_key = races.json()[0]["race_key"]

        forecast = _get(client, f"/api/v1/races/{race_key}/forecast", headers=headers)
        if forecast.status_code != 200:
            return Check(
                "予測モデル", "warning", f"予想が取得できませんでした（{forecast.status_code}）。"
            )
    except httpx.HTTPError as exc:
        return Check("予測モデル", "warning", f"確認できません（{type(exc).__name__}）。")

    version = str(forecast.json().get("model_version", ""))
    if version.startswith("rule"):
        return Check(
            "予測モデル",
            "critical",
            f"ルールベースで動いています（{version}）。LightGBM モデルを読めていません。",
            "MODELS_DIR とイメージ内の /app/models を確認してください。例外は出ません。",
        )
    return Check("予測モデル", "ok", f"学習済みモデルで動いています（{version}）。")


_MARKS: dict[Severity, str] = {"ok": "✓", "warning": "!", "critical": "✗"}


def main() -> None:
    args = _parse_args()
    base_url = args.base_url.rstrip("/")

    with httpx.Client(base_url=base_url, timeout=_TIMEOUT, follow_redirects=True) as client:
        checks = [_check_health(client)]
        if checks[0].severity == "critical":
            _report(checks)
            raise SystemExit(1)

        checks.append(_check_readiness(client))
        checks.extend(_check_public_api_protected(client, args.token))
        checks.append(_check_cors(client))
        checks.append(_check_forecaster(client, args.token))

    _report(checks)
    if any(check.severity == "critical" for check in checks):
        raise SystemExit(1)


def _report(checks: list[Check]) -> None:
    print(f"■ 確認結果（{len(checks)} 項目）\n")
    for check in checks:
        print(f"  {_MARKS[check.severity]} {check.name}: {check.detail}")
        if check.action:
            print(f"      → {check.action}")

    print("\n■ 外からは確認できない項目")
    print("  - RATE_LIMIT_TRUSTED_PROXIES: ロードバランサ配下では 1 を設定すること。")
    print("    0 のままだと全利用者が同じキーへ集約され、制限が「全体でN回/分」になる。")
    print("  - 接続プーラーのモード: pg8000 は session モードを使うこと。")

    failed = sum(1 for c in checks if c.severity == "critical")
    warned = sum(1 for c in checks if c.severity == "warning")
    print()
    if failed:
        print(f"✗ 対応が要る項目が {failed} 件あります。")
    elif warned:
        print(f"! 確認したい項目が {warned} 件あります（致命的な問題は見つかりませんでした）。")
    else:
        print("✓ 確認したすべての項目が意図どおりでした。")


if __name__ == "__main__":
    main()
