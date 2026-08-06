from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


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
    """
    return create_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=pool_recycle_seconds,
    )


def build_session_maker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, autocommit=False, autoflush=False)
