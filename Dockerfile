# ===========================================================================
# Afterglow - Multi-stage Dockerfile
# ===========================================================================
# 사용법:
#   docker build --target backend -t afterglow-api .
#   docker build --target frontend -t afterglow .
#
# docker-compose에서는 build.target으로 자동 지정됩니다.
# ===========================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Backend 스테이지
# ─────────────────────────────────────────────────────────────────────────────

# ── Backend 빌더 (gcc 컴파일용, 최종 이미지에 포함되지 않음) ─────────────────
FROM python:3.12-slim AS backend-builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/afterglow-crypto/ /services/afterglow-crypto/
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"

# ── Backend 프로덕션 (깨끗한 slim 이미지, gcc 없음) ──────────────────────────
FROM python:3.12-slim AS backend

WORKDIR /app

# 빌더에서 컴파일된 가상환경만 복사 (gcc/libc6-dev 제외)
COPY --from=backend-builder /app/.venv /app/.venv

COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/app/ ./app/
COPY backend/tofu/ ./tofu/
COPY backend/scripts/ ./scripts/

# .pyc 직접 사용으로 cold start 가속
RUN python -m compileall -q app/

# OpenTofu CLI 설치 (MPL-2.0, ~80MB)
ARG TOFU_VERSION=1.8.3
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ffmpeg qemu-utils ceph-common \
    && curl -fsSL "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_amd64.zip" -o /tmp/tofu.zip \
    && unzip /tmp/tofu.zip tofu -d /usr/local/bin/ \
    && rm /tmp/tofu.zip \
    && apt-get purge -y --auto-remove curl unzip \
    && rbd --version \
    && rados --version \
    && rm -rf /var/lib/apt/lists/*

RUN rm -rf /tmp/* /root/.cache

RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app

# uv 없이 직접 venv 바이너리 사용 → 시작 시간 ~300ms 단축
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Backend 개발 스테이지 (docker-compose.override.yml에서 사용) ────────────
# 소스코드를 볼륨 마운트하여 실시간 반영, reload 모드로 실행
FROM backend-builder AS backend-dev
COPY backend/app/ ./app/
# dev 의존성(pytest 등) 설치
RUN uv sync --frozen --no-install-project
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser
ENV PATH="/app/.venv/bin:$PATH"
# named volume 캐시가 오래된 .venv를 갖고 있어도 의존성 자동 동기화
CMD ["sh", "-c", "uv sync --frozen --no-install-project && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

# ─────────────────────────────────────────────────────────────────────────────
# Notion integration worker stage
# OpenTofu/curl/unzip and API-only dependencies are omitted.
# Usage:
#   docker build --target worker -t afterglow-worker .

# ── Worker 빌더 (worker 의존성 그룹만 설치) ──────────────────────────────────
FROM python:3.12-slim AS worker-builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/afterglow-crypto/ /services/afterglow-crypto/
COPY backend/pyproject.toml backend/uv.lock ./
# worker 의존성 그룹만 설치 (fastapi/uvicorn/boto3 등 API 전용 패키지 제외)
RUN uv sync --frozen --no-dev --no-install-project --only-group worker
ENV PATH="/app/.venv/bin:$PATH"

# ── Worker 프로덕션 (깨끗한 slim 이미지, OpenTofu/curl/unzip 없음) ───────────
FROM python:3.12-slim AS worker

WORKDIR /app

# worker-builder에서 컴파일된 경량 가상환경 복사
COPY --from=worker-builder /app/.venv /app/.venv

COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/app/ ./app/
# tofu/ 디렉토리는 API 전용 (OpenTofu CLI 연동) — 워커에 불필요하여 제외

# .pyc 직접 사용으로 cold start 가속
RUN python -m compileall -q app/

RUN rm -rf /tmp/* /root/.cache

RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app

ENV PATH="/app/.venv/bin:$PATH"

USER appuser

# Default command for the sole remaining Afterglow integration worker.
CMD ["python", "-m", "app.notion_worker"]


# ─────────────────────────────────────────────────────────────────────────────
# Frontend 스테이지
# ─────────────────────────────────────────────────────────────────────────────

FROM oven/bun:1 AS frontend-builder

WORKDIR /app

COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile

COPY frontend/ .
RUN bun run build

FROM node:20-alpine AS frontend

WORKDIR /app

COPY --from=frontend-builder /app/build ./build
COPY --from=frontend-builder /app/package.json ./
COPY --from=frontend-builder /app/scripts ./scripts
RUN npm install --omit=dev --ignore-scripts \
    && adduser -D appuser \
    && chown -R appuser:appuser /app

USER appuser

# EXPOSE 3080
ENV PORT=3080

CMD ["node", "scripts/run-with-file-log.mjs", "node", "build"]

# ── Frontend 개발 스테이지 (docker-compose.override.yml에서 사용) ────────────
# Frontend 개발 스테이지
# 볼륨 마운트 시 소스코드 실시간 반영, 아닐 경우 이미지 내 소스 사용
FROM oven/bun:1 AS frontend-dev

WORKDIR /app

COPY frontend/package.json frontend/bun.lock* ./
RUN bun install

COPY frontend/ .

# EXPOSE 3080
ENV PORT=3080

CMD ["bun", "scripts/run-with-file-log.mjs", "bun", "run", "dev:raw", "--host", "0.0.0.0", "--port", "3080"]
