from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
CommentGeneratorMode = Literal["rule", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    database_url: str = "postgresql+pg8000://pci:pci_dev@localhost:5432/pci_dev"
    comment_generator_mode: CommentGeneratorMode = "rule"
    gemini_api_key: str | None = None
    gemini_model: str = DEFAULT_GEMINI_MODEL
    ingest_token: str | None = None  # Bearer token for /internal/ingest/* endpoints
    public_api_token: str | None = None  # Bearer token for /api/v1/* endpoints
    # ブラウザから直接叩くことを許すオリジン（カンマ区切り）。
    #
    # web は Next.js のサーバコンポーネントから呼ぶため、通常の動作に CORS は要らない
    # （`apps/web/src/lib/api.ts` 参照）。既定をローカル開発の2つに絞ってあるのは、
    # 手元でブラウザから叩く場合のためだけ。**本番オリジンは環境変数で明示すること。**
    #
    # 以前は `allow_origins=["*"]` だった。利点が無い一方、公開時は任意のサイトから
    # JRA-VAN 由来のデータを読み出せる状態になる（CLAUDE.md「生データ再配布は禁止前提」）。
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # 公開参照APIの1分あたり上限（クライアント単位）。0 で無効。
    # 目的は無制限スクレイピングの抑止であって、正規利用の妨害ではない。
    # 1レース閲覧で数リクエスト、一覧で十数リクエスト程度を想定して余裕を持たせる。
    rate_limit_per_minute: int = 120
    # 前段に置く信頼できるプロキシの段数。
    #
    # PaaS のロードバランサ配下では接続元IPが常にプロキシになり、全利用者が同じ
    # キーへ集約されてしまう。かといって `X-Forwarded-For` を無条件に信じると、
    # ヘッダ詐称で制限を回避できる。**実際の構成の段数を明示したときだけ**
    # そのヘッダを使う。既定0＝接続元IPをそのまま使う（プロキシ無しの想定）。
    rate_limit_trusted_proxies: int = 0

    def cors_origin_list(self) -> list[str]:
        """設定文字列をオリジンの一覧へ変換する。空なら CORS を一切許可しない。"""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
