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

# ── OpenTofu installer (architecture-aware, verified download) ──────────────
FROM python:3.12-slim AS tofu-installer

ARG TOFU_VERSION=1.8.3
ARG TARGETARCH
ARG TOFU_SHA256_AMD64=dc44b452a407648a40900eea5ceca2dd586dd084ae085863dba997331dcf8225
ARG TOFU_SHA256_ARM64=c3ea55a86aaf22729be63371176fdefa40ae9632a6b620c64b98d7fb3a13205e

RUN case "${TARGETARCH}" in \
        amd64) tofu_sha256="${TOFU_SHA256_AMD64}" ;; \
        arm64) tofu_sha256="${TOFU_SHA256_ARM64}" ;; \
        *) echo "Unsupported OpenTofu target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && curl --fail --show-error --location \
        --retry 5 --retry-all-errors --retry-delay 2 --retry-max-time 120 \
        --connect-timeout 15 \
        "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_${TARGETARCH}.zip" \
        -o /tmp/tofu.zip \
    && echo "${tofu_sha256}  /tmp/tofu.zip" | sha256sum --check --strict - \
    && unzip /tmp/tofu.zip tofu -d /usr/local/bin/ \
    && /usr/local/bin/tofu version

# ── Backend 빌더 (gcc 컴파일용, 최종 이미지에 포함되지 않음) ─────────────────
FROM python:3.12-slim AS backend-builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/afterglow-crypto/pyproject.toml /services/afterglow-crypto/pyproject.toml
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-install-package afterglow-crypto --link-mode=copy
COPY services/afterglow-crypto/afterglow_crypto/ /services/afterglow-crypto/afterglow_crypto/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --link-mode=copy
ENV PATH="/app/.venv/bin:$PATH"

# ── Backend 공통 런타임 (애플리케이션 소스와 독립된 시스템 패키지) ───────────
FROM python:3.12-slim AS backend-runtime

WORKDIR /app


RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg qemu-utils ceph-common \
    && rbd --version \
    && rados --version \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos "" appuser \
    && chown appuser:appuser /app

# uv 없이 직접 venv 바이너리 사용 → 시작 시간 ~300ms 단축
ENV PATH="/app/.venv/bin:$PATH"

# OpenTofu 변경도 OS 패키지 설치 캐시를 무효화하지 않는다.
COPY --from=tofu-installer /usr/local/bin/tofu /usr/local/bin/tofu

# ── Backend 프로덕션 (의존성 뒤에 소스, gcc 없음) ───────────────────────────
FROM backend-runtime AS backend

COPY --from=backend-builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser backend/pyproject.toml backend/uv.lock ./
COPY --chown=appuser:appuser backend/tofu/ ./tofu/
COPY --chown=appuser:appuser backend/scripts/ ./scripts/
COPY --chown=appuser:appuser backend/app/ ./app/

USER appuser
# 소스 변경 시에는 앱 bytecode만 다시 생성한다.
RUN python -m compileall -q app/


CMD ["uvicorn", "app.middleware.traffic_address:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

# ── Backend 개발 스테이지 (docker-compose.override.yml에서 사용) ────────────
# 소스코드를 볼륨 마운트하여 실시간 반영, reload 모드로 실행
FROM backend-builder AS backend-dev
# dev 의존성(pytest 등) 설치
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --link-mode=copy
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
COPY --chown=appuser:appuser backend/app/ ./app/
USER appuser
ENV PATH="/app/.venv/bin:$PATH"
# named volume 캐시가 오래된 .venv를 갖고 있어도 의존성 자동 동기화
CMD ["sh", "-c", "uv sync --frozen --no-install-project && uvicorn app.middleware.traffic_address:create_app --factory --host 0.0.0.0 --port 8000 --reload --no-proxy-headers"]

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

COPY services/afterglow-crypto/pyproject.toml /services/afterglow-crypto/pyproject.toml
COPY backend/pyproject.toml backend/uv.lock ./
# worker 의존성 그룹만 설치 (fastapi/uvicorn/boto3 등 API 전용 패키지 제외)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --only-group worker \
        --no-install-package afterglow-crypto --link-mode=copy
COPY services/afterglow-crypto/afterglow_crypto/ /services/afterglow-crypto/afterglow_crypto/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --only-group worker --link-mode=copy
ENV PATH="/app/.venv/bin:$PATH"

# ── Worker 프로덕션 (깨끗한 slim 이미지, OpenTofu/curl/unzip 없음) ───────────
FROM python:3.12-slim AS worker

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser \
    && chown appuser:appuser /app

# worker-builder에서 컴파일된 경량 가상환경 복사
COPY --from=worker-builder --chown=appuser:appuser /app/.venv /app/.venv

COPY --chown=appuser:appuser backend/pyproject.toml backend/uv.lock ./
COPY --chown=appuser:appuser backend/app/ ./app/
# tofu/ 디렉토리는 API 전용 (OpenTofu CLI 연동) — 워커에 불필요하여 제외

USER appuser
# .pyc 직접 사용으로 cold start 가속
RUN python -m compileall -q app/


ENV PATH="/app/.venv/bin:$PATH"


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

RUN adduser -D appuser && chown appuser:appuser /app
USER appuser

COPY --chown=appuser:appuser frontend/package.json frontend/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts

COPY --from=frontend-builder --chown=appuser:appuser /app/build ./build
COPY --chown=appuser:appuser frontend/scripts/ ./scripts


# EXPOSE 3080
ENV PORT=3080

CMD ["node", "scripts/run-with-file-log.mjs", "node", "build"]

# ── Native OCI-root VM: no container engine inside the guest ─────────────────
# BuildKit produces the filesystem; Palimpsest's Linux amd64/KVM stage-1 boots it.
# The existing frontend/backend/worker targets remain independent deliverables.
FROM node:22-bookworm-slim AS native-node
FROM oven/bun:1 AS native-frontend-dependencies
WORKDIR /app/frontend
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --production --frozen-lockfile

FROM backend-builder AS native-dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --group worker --link-mode=copy

FROM backend-runtime AS native-runtime
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends mariadb-server mariadb-client redis-server \
    && rm -rf /var/lib/apt/lists/* /var/lib/mysql/* \
    && install -d -m 0700 -o appuser -g appuser /var/lib/afterglow \
    && install -d -m 0755 -o appuser -g appuser /app/logs \
    && ln -s /var/lib/afterglow/afterglow.conf /app/afterglow.conf
ENV PORT=3080 HOST=0.0.0.0

FROM native-runtime AS native-vm
COPY --from=native-dependencies --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=native-node /usr/local/bin/node /usr/local/bin/node
COPY --from=native-frontend-dependencies --chown=appuser:appuser /app/frontend/node_modules /app/frontend/node_modules
COPY --from=frontend-builder --chown=appuser:appuser /app/build /app/frontend/build
COPY --chown=appuser:appuser frontend/package.json /app/frontend/package.json
COPY --chown=appuser:appuser frontend/scripts/ /app/frontend/scripts/
COPY --from=backend --chown=appuser:appuser /app/app /app/app
COPY --from=backend --chown=appuser:appuser /app/tofu /app/tofu
COPY --from=backend --chown=appuser:appuser /app/scripts /app/scripts
COPY --chown=appuser:appuser backend/pyproject.toml backend/uv.lock /app/
USER appuser
ENTRYPOINT ["/app/.venv/bin/python", "/app/scripts/native_vm.py"]
CMD []

# ── Native cloud VM: 소스와 독립된 커널/부팅 패키지 설치 ────────────────────
# Debian linux/amd64 only. Adds the same-distro kernel + initramfs, BIOS GRUB
# modules, systemd as PID 1, cloud-init, sshd and afterglow-native.service
# (the native supervisor as appuser). Still no container engine in the guest.
# Build with --platform linux/amd64 --output type=tar; then
# scripts/export_native_cloud.py writes the BIOS-bootable raw disk. This is the
# OCI root plus declared bootability additions, not the protected OCI-root
# stage-1 path. The image ENTRYPOINT is unused when the disk boots /sbin/init.
FROM native-runtime AS native-cloud-runtime
USER root
ARG DEBIAN_FRONTEND=noninteractive
RUN test "$(dpkg --print-architecture)" = amd64 \
    && install -d -m 0755 /etc/initramfs-tools/conf.d \
    && printf 'RESUME=none\n' > /etc/initramfs-tools/conf.d/afterglow-native-cloud \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        linux-image-amd64 initramfs-tools grub-pc-bin grub2-common \
        systemd systemd-sysv systemd-resolved systemd-timesyncd dbus udev kmod \
        cloud-init cloud-guest-utils netcat-openbsd openssh-server sudo \
        e2fsprogs xfsprogs fdisk util-linux iproute2 iputils-ping procps ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && test "$(find /boot -maxdepth 1 -name 'vmlinuz-*' -type f | wc -l)" = 1 \
    && kernel="$(basename "$(find /boot -maxdepth 1 -name 'vmlinuz-*' -type f)" | sed 's/^vmlinuz-//')" \
    && test -s "/boot/initrd.img-${kernel}" \
    && test -f /usr/lib/grub/i386-pc/boot.img \
    && test -f /usr/lib/grub/i386-pc/modinfo.sh \
    && command -v mount.ceph >/dev/null \
    && test -x /usr/bin/python3 \
    && test -n "$(find "/usr/lib/modules/${kernel}" -name 'ceph.ko*' -print -quit)"
COPY --chmod=0644 backend/scripts/native-cloud/afterglow-native.service /etc/systemd/system/afterglow-native.service
COPY --chmod=0755 backend/scripts/native-cloud/afterglow-native-prepare /usr/local/libexec/afterglow-native-prepare
COPY --chmod=0644 backend/scripts/native-cloud/95_afterglow_native.cfg /etc/cloud/cloud.cfg.d/95_afterglow_native.cfg
COPY --chmod=0644 backend/scripts/native-cloud/ssh-host-keys.conf /etc/systemd/system/ssh.service.d/afterglow-host-keys.conf
COPY --chmod=0644 backend/scripts/native-cloud/grub-default.cfg /etc/default/grub.d/afterglow-native-cloud.cfg
# The supervisor owns MariaDB/Redis as appuser; the distro system services
# would collide with it. No machine identity, host keys or cloud-init instance
# state is baked: each booted disk generates its own.
RUN systemctl disable mariadb.service redis-server.service \
    && systemctl mask mariadb.service redis-server.service \
    && systemctl enable systemd-networkd.service systemd-resolved.service systemd-timesyncd.service \
        ssh.service afterglow-native.service \
    && install -d -m 0700 -o root -g root /etc/afterglow \
    && rm -f /usr/sbin/policy-rc.d /etc/ssh/ssh_host_* /var/lib/systemd/random-seed /var/lib/systemd/credential.secret \
    && rm -rf /var/lib/cloud/* /var/log/cloud-init*.log \
    && : > /etc/machine-id \
    && if [ -e /var/lib/dbus/machine-id ] && [ ! -L /var/lib/dbus/machine-id ]; then rm -f /var/lib/dbus/machine-id; fi \
    && test -L /app/afterglow.conf \
    && test "$(readlink /app/afterglow.conf)" = /var/lib/afterglow/afterglow.conf \
    && test -z "$(ls -A /var/lib/afterglow)"

FROM native-cloud-runtime AS native-cloud-vm
COPY --from=native-node /usr/local/bin/node /usr/local/bin/node
COPY --from=native-vm --chown=appuser:appuser /app /app
ENTRYPOINT ["/app/.venv/bin/python", "/app/scripts/native_vm.py"]
CMD []
USER appuser

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
