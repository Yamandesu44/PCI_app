import logging
import ssl
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

_logger = logging.getLogger(__name__)

# libpq の sslmode のうち、暗号化はするが証明書を検証しないもの。
# 検証しないため中間者攻撃を防げない。可能なら verify-full を使う。
_UNVERIFIED_SSL_MODES = frozenset({"allow", "prefer", "require"})
_VERIFIED_SSL_MODES = frozenset({"verify-ca", "verify-full"})

# 手元・コンテナ内のDB。ここへの接続は公衆網を通らないため暗号化を求めない。
# `db` は docker-compose のサービス名。
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db", ""})


def _warn_if_unencrypted(url: URL) -> None:
    """公衆網へ平文で出ようとしていたら警告する。

    マネージドDBの接続文字列は `sslmode` を含まないことがあり、そのまま貼ると
    **暗号化なしで接続できてしまう**。接続は成功し、動作も変わらないので、
    気付く機会が無いまま資格情報とデータが平文で流れ続ける。
    """
    if url.host and url.host.lower() not in _LOCAL_HOSTS and "sslmode" not in url.query:
        _logger.warning(
            "DATABASE_URL に sslmode がありません。%s へ暗号化なしで接続します。"
            "マネージドDBへ繋ぐ場合は ?sslmode=require を付けてください。",
            url.host,
        )


def _split_pg8000_ssl(url: URL) -> tuple[URL, dict[str, Any]]:
    """`sslmode` / `sslrootcert` を URL から外し、pg8000 の `ssl_context` へ翻訳する。

    **pg8000 は `sslmode` を受け取れない。** マネージドDBが配る接続文字列は
    `?sslmode=require` を含むことが多く、そのまま `DATABASE_URL` へ入れると

        TypeError: connect() got an unexpected keyword argument 'sslmode'

    で接続そのものが失敗する。psycopg2 なら通るため、ドライバを変えた途端に
    壊れる類の落とし穴。利用者が接続文字列をそのまま貼れるよう、ここで吸収する。
    """
    query = dict(url.query)
    mode = str(query.pop("sslmode", "")).lower()
    root_cert = query.pop("sslrootcert", None)
    stripped = url.set(query=query)

    if not mode or mode == "disable":
        return stripped, {}

    context = ssl.create_default_context(
        cafile=str(root_cert) if root_cert else None,
    )
    if mode in _UNVERIFIED_SSL_MODES:
        # libpq の require は「暗号化するが検証しない」。同じ意味に揃える。
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif mode in _VERIFIED_SSL_MODES:
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = mode == "verify-full"
    else:
        raise ValueError(f"未知の sslmode です: {mode}")

    return stripped, {"ssl_context": context}


def prepare_connection(database_url: str) -> tuple[URL, dict[str, Any]]:
    """接続文字列を、ドライバがそのまま受け取れる形へ整える。

    **エンジンを組む場所は必ずここを通すこと。** SSL の翻訳を各所で書くと、
    通した経路だけが動いて他は繋がらない。実際、alembic は独自にエンジンを
    組んでいたため、アプリは繋がるのにマイグレーションだけ `sslmode` で
    落ちる状態になっていた。プールの設定は呼び出し側で決める（マイグレーションは
    使い捨てなのでプールを持たない）。
    """
    url = make_url(database_url)
    _warn_if_unencrypted(url)
    connect_args: dict[str, Any] = {}
    if url.drivername.endswith("pg8000"):
        url, connect_args = _split_pg8000_ssl(url)
    return url, connect_args


def build_engine(
    database_url: str,
    pool_size: int = 3,
    max_overflow: int = 2,
    pool_recycle_seconds: int = 1800,
) -> Engine:
    """DB エンジンを組む。

    既定値はサーバーレス実行環境（Cloud Run 等）を前提にしている。

    **接続数**: SQLAlchemy の既定は `pool_size=5, max_overflow=10` で、1プロセスが
    最大15本を握る。インスタンスが増減する環境ではこれがそのまま台数倍になり、
    max-instances=3 なら45本。無料枠の Postgres は同時接続数の上限が低いことが多く、
    上限に当たると新しいインスタンスがDBへ一切繋げなくなる。既定を絞って
    3+2=5本/プロセスとし、台数倍しても収まるようにする。

    **`pool_pre_ping`**: サーバーレスのDBはアイドルで自動停止し、再開時に既存の
    接続が切れる。プールに残った死んだ接続をそのまま使うと、**最初のリクエストだけが
    接続エラーで失敗する**。使う前に軽く疎通を確認し、駄目なら黙って張り直す。

    **`pool_recycle`**: DBやプロキシ側が一定時間で接続を切ることがある。こちらから
    先に捨てておかないと、切られた接続を掴んだリクエストが失敗する。

    **SSL**: pg8000 を使う場合、接続文字列の `sslmode` は `ssl_context` へ翻訳する
    （`_split_pg8000_ssl` 参照）。マネージドDBの接続文字列をそのまま貼れるようにするため。
    """
    url, connect_args = prepare_connection(database_url)

    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=pool_recycle_seconds,
        connect_args=connect_args,
    )


def build_session_maker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, autocommit=False, autoflush=False)
