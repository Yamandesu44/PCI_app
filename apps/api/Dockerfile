# PCI App API — 本番用イメージ。
#
# デプロイ先（Railway / Render / Fly.io など）を問わず動くよう、PaaS 固有の仕組みは
# 使わない。ポートは PORT 環境変数で受ける（未設定なら 8000）。
#
# Python は 3.11 に固定する。`requires-python = ">=3.11"` の下限であり、CI の型検査も
# 同じ版で走らせている。3.12 にすると numpy 2.5 系が入り、他の版と依存が揃わなくなる。

# ---- builder: 依存を仮想環境へ入れる ----
FROM python:3.11-slim AS builder

# lightgbm は OpenMP ランタイムを必要とする。ビルド時にも実行時にも要る。
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 依存の解決とビルドを一度に行う。空パッケージを置いて依存だけ先に入れる小細工は
# ビルドバックエンド（hatchling）の挙動に依存して壊れやすいので使わない。
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install ".[ml]"

# ---- runtime ----
FROM python:3.11-slim AS runtime

# libgomp1 は lightgbm の実行に必要。build-essential は持ち込まない。
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 pci

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# マイグレーションは起動時ではなくデプロイ手順で流す（`alembic upgrade head`）。
# 同時起動した複数インスタンスが競合しないよう、アプリ側では自動実行しない。
COPY alembic.ini ./
COPY alembic/ ./alembic/
# LightGBM モデル（約2MB）。既定パスは apps/api からの相対なのでこの位置に置く。
COPY models/ ./models/

USER pci

EXPOSE 8000

# /health は DB を見ない純粋な生存確認。DB 込みの判定は /ready を使う。
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request;\
urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT','8000')}/health\").read()"

# PORT を展開するためシェル形式。exec でシグナルを uvicorn へ渡す。
CMD exec uvicorn pci.presentation.app:app --host 0.0.0.0 --port "${PORT}"
