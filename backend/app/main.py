# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------
import logging
import logging.handlers
import os

_STANDARD_LOG_KEYS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _STANDARD_LOG_KEYS and k != "message":
                entry[k] = v
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def _setup_logging() -> None:
    from app.config import get_settings

    cfg = get_settings()

    formatter = _JSONFormatter()
    root = logging.getLogger()
    root.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    log_path = cfg.log_file_path
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        if cfg.log_rotation_type == "time":
            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_path,
                when=cfg.log_rotation_when,
                interval=cfg.log_rotation_interval,
                backupCount=cfg.log_backup_count,
                encoding="utf-8",
            )
        else:
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=cfg.log_max_bytes,
                backupCount=cfg.log_backup_count,
                encoding="utf-8",
            )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        pass  # 로그 디렉터리 없으면 파일 핸들러 없이 진행

    level = getattr(logging, cfg.log_level.upper(), logging.INFO)
    root.setLevel(level)
    logging.getLogger("openstack").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("keystoneauth1").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


_setup_logging()
_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import 프로파일링 — 로거 설정 전에 실행되므로 print 대신 리스트에 기록
# ---------------------------------------------------------------------------
import time as _time

_t0 = _time.perf_counter()
_import_times: list[tuple[str, float]] = []


def _mark(label: str) -> None:
    _logger.info("imported %s at %.3fs", label, _time.perf_counter() - _t0)
    _import_times.append((label, _time.perf_counter()))


# ---------------------------------------------------------------------------
# stdlib
# ---------------------------------------------------------------------------
import asyncio
import json
import time
from datetime import UTC, datetime

_mark("stdlib")

# ---------------------------------------------------------------------------
# 프레임워크 (fastapi, slowapi)
# ---------------------------------------------------------------------------
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler as _default_http_handler
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

_mark("fastapi")

# ---------------------------------------------------------------------------
# app.api.common
# ---------------------------------------------------------------------------
from app.api.common import (
    dashboard_router,
    grafana_auth_router,
    libraries_router,
    metrics_router,
    sd_targets_router,
    site_router,
    user_dashboard_router,
)
from app.api.common.metrics import record_request as _record_request

_mark("api.common")

# ---------------------------------------------------------------------------
# app.api.compute
# ---------------------------------------------------------------------------
from app.api.compute import (
    flavors_router,
    images_router,
    instance_health_router,
    instance_metrics_router,
    instances_router,
    keypairs_router,
)

_mark("api.compute")

# ---------------------------------------------------------------------------
# app.api.container
# ---------------------------------------------------------------------------
from app.api.container import clusters_router, containers_router

_mark("api.container")

# ---------------------------------------------------------------------------
# app.api.identity (admin, auth, sub-routers)
# ---------------------------------------------------------------------------
from app.api.identity import admin_router, auth_router
from app.api.identity.admin_activity import router as admin_activity_router
from app.api.identity.admin_flavors import router as admin_flavors_router
from app.api.identity.admin_gpu import router as admin_gpu_router
from app.api.identity.admin_identity import router as admin_identity_router
from app.api.identity.admin_images import router as admin_images_router
from app.api.identity.admin_instances import router as admin_instances_router
from app.api.identity.admin_libraries import router as admin_libraries_router
from app.api.identity.admin_notion import router as admin_notion_router
from app.api.identity.admin_orphans import router as admin_orphans_router
from app.api.identity.admin_secrets import router as admin_secrets_router
from app.api.identity.admin_services import router as admin_services_router
from app.api.identity.profile import router as profile_router
from app.api.identity.profile_activity import router as profile_activity_router

_mark("api.identity")

# ---------------------------------------------------------------------------
# app.api.k3s + network + storage
# ---------------------------------------------------------------------------
from app.api.k3s import k3s_callback_router, k3s_clusters_router, k3s_health_router
from app.api.network import (
    loadbalancers_router,
    networks_router,
    routers_router,
    security_groups_router,
)
from app.api.storage import (
    file_storage_router,
    security_services_router,
    share_networks_router,
    share_snapshots_router,
    volume_backups_router,
    volume_snapshots_router,
    volumes_router,
)

_mark("api.k3s_network_storage")

# ---------------------------------------------------------------------------
# 기타 앱 유틸리티
# ---------------------------------------------------------------------------
from app.api.deps import get_token_info
from app.rate_limit import limiter
from app.utils.version import read_app_version

_mark("misc")


# ---------------------------------------------------------------------------
# Import 프로파일링 결과 출력 (로거가 준비된 시점에 1회)
# ---------------------------------------------------------------------------
_prev = _t0
_profile: dict[str, float] = {}
for _label, _ts in _import_times:
    _profile[_label] = round((_ts - _prev) * 1000, 1)
    _prev = _ts
_profile["total"] = round((_prev - _t0) * 1000, 1)
_logger.info("import-profile", extra={"import_ms": _profile})
del _prev, _label, _ts, _profile  # 모듈 네임스페이스 정리

_is_production = os.environ.get("AFTERGLOW_ENV", "development") == "production"


app = FastAPI(
    title="Afterglow",
    description="OpenStack VM 배포 + OverlayFS 마운트 웹 플랫폼",
    version=read_app_version(),
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(HTTPException)
async def sanitized_http_exception_handler(request: Request, exc: HTTPException):
    """5xx 에러의 내부 상세 정보를 클라이언트에 노출하지 않고 로그에만 기록.

    400/4xx 에 chained __cause__ 가 있으면 진짜 원인을 함께 로깅 — FastAPI 가
    request body parsing 예외(MultiPartException 등)를 generic 400 으로 wrap 해
    detail 만으로 진단 어려움 대응.
    """
    if exc.status_code >= 500:
        _logger.error(
            "HTTP %d: %s %s — %s",
            exc.status_code,
            request.method,
            request.url.path,
            exc.detail,
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": "내부 서버 오류"})
    if exc.status_code == 400:
        cause = getattr(exc, "__cause__", None)
        _logger.warning(
            "HTTP 400: %s %s — detail=%r cause=%s",
            request.method,
            request.url.path,
            exc.detail,
            f"{type(cause).__name__}: {cause}" if cause else "<none>",
        )
    return await _default_http_handler(request, exc)


try:
    from starlette.requests import ClientDisconnect as _ClientDisconnect
except ImportError:  # pragma: no cover - older starlette
    _ClientDisconnect = None  # type: ignore[assignment]


if _ClientDisconnect is not None:

    @app.exception_handler(_ClientDisconnect)
    async def client_disconnect_handler(request: Request, exc):  # type: ignore[no-untyped-def]
        """클라이언트가 multipart body 수신 도중 연결을 끊은 경우.

        이 시점에는 endpoint 함수가 아직 호출되지 않아 자체 cancel 로깅이
        남지 않으므로 여기서 명시적으로 기록한다. 클라는 이미 disconnect 라
        응답은 도달하지 않지만 access log 분류용으로 499 반환.
        """
        _logger.info("client disconnect: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=499, content={"detail": "클라이언트 연결 종료"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """처리되지 않은 예외를 로그에 기록하고 500을 반환."""
    _logger.exception("Unhandled exception: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "내부 서버 오류"})


# 보안 응답 헤더: API 서버이므로 제한적 CSP 적용
_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    # dev 모드에서 /docs, /redoc 경로는 Swagger UI 로딩을 위해 보안 헤더 생략
    path = request.url.path.rstrip("/")
    if not _is_production and path in _DOCS_PATHS:
        return response
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


# CORS: credentials 사용 시 allow_origins=["*"] 는 브라우저가 거부하므로
# 요청 Origin을 동적으로 허용 (개발 환경)
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    _record_request(request.method, request.url.path, response.status_code, duration_ms)
    if not request.url.path.startswith("/api/health"):
        _logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
    return response


_CORS_ALLOW_HEADERS = "Content-Type, X-Auth-Token, X-Project-Id, Authorization"
_CORS_ALLOW_METHODS = "GET, POST, PUT, DELETE, OPTIONS, PATCH"


def _get_allowed_origins() -> set[str]:
    from app.config import get_settings

    return set(get_settings().cors_origin_list)


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin", "")
    response = await call_next(request)
    if origin and origin in _get_allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = _CORS_ALLOW_METHODS
        response.headers["Access-Control-Allow-Headers"] = _CORS_ALLOW_HEADERS
        response.headers["Vary"] = "Origin"
    return response


@app.options("/{rest_of_path:path}")
async def options_handler(request: Request, rest_of_path: str):
    """OPTIONS preflight 전용 핸들러."""
    origin = request.headers.get("origin", "")
    allowed = _get_allowed_origins()
    if origin not in allowed:
        return JSONResponse(content="Forbidden", status_code=403)
    return JSONResponse(
        content="OK",
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": _CORS_ALLOW_METHODS,
            "Access-Control-Allow-Headers": _CORS_ALLOW_HEADERS,
            "Access-Control-Max-Age": "600",
            "Vary": "Origin",
        },
    )


# Identity
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
# admin_instances_router를 admin_router보다 먼저 등록 (정적 경로 /instances/async 우선 매칭)
app.include_router(admin_instances_router, prefix="/api/admin", tags=["admin-instances"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(admin_services_router, prefix="/api/admin", tags=["admin-services"])
app.include_router(admin_flavors_router, prefix="/api/admin", tags=["admin-flavors"])
app.include_router(admin_identity_router, prefix="/api/admin", tags=["admin-identity"])
app.include_router(admin_gpu_router, prefix="/api/admin", tags=["admin-gpu"])
app.include_router(admin_libraries_router, prefix="/api/admin/libraries", tags=["admin-libraries"])
app.include_router(admin_notion_router, prefix="/api/admin", tags=["admin-notion"])
app.include_router(admin_images_router, prefix="/api/admin", tags=["admin-images"])
app.include_router(profile_router, prefix="/api/profile", tags=["profile"])
app.include_router(profile_activity_router, prefix="/api/profile/activity", tags=["profile-activity"])
app.include_router(admin_activity_router, prefix="/api/admin", tags=["admin-activity"])
app.include_router(admin_orphans_router, prefix="/api/admin", tags=["admin-orphans"])
# Compute
app.include_router(images_router, prefix="/api/images", tags=["images"])
app.include_router(flavors_router, prefix="/api/flavors", tags=["flavors"])
# instance_health_router을 instances_router보다 먼저 등록 (/health 경로 충돌 방지)
app.include_router(instance_health_router, prefix="/api/instances", tags=["instance-health"])
app.include_router(instance_metrics_router, prefix="/api/instances", tags=["instance-metrics"])
app.include_router(instances_router, prefix="/api/instances", tags=["instances"])
app.include_router(keypairs_router, prefix="/api/keypairs", tags=["keypairs"])
# Storage (backups 먼저 등록 — /api/volumes/{id} catch-all 보다 앞에)
app.include_router(volume_backups_router, prefix="/api/volumes/backups", tags=["volume-backups"])
app.include_router(volume_snapshots_router, prefix="/api/volume-snapshots", tags=["volume-snapshots"])
app.include_router(volumes_router, prefix="/api/volumes", tags=["volumes"])
# Network
app.include_router(networks_router, prefix="/api/networks", tags=["networks"])
app.include_router(routers_router, prefix="/api/routers", tags=["routers"])
app.include_router(loadbalancers_router, prefix="/api/loadbalancers", tags=["loadbalancers"])
app.include_router(security_groups_router, prefix="/api/security-groups", tags=["security-groups"])
# Optional services — config.toml [services] 섹션에서 활성화
from app.config import get_settings as _get_cfg

_svc_cfg = _get_cfg()
if _svc_cfg.service_manila_enabled:
    app.include_router(file_storage_router, prefix="/api/file-storage", tags=["file-storage"])
    app.include_router(share_snapshots_router, prefix="/api/share-snapshots", tags=["share-snapshots"])
    app.include_router(share_networks_router, prefix="/api/share-networks", tags=["share-networks"])
    app.include_router(
        security_services_router,
        prefix="/api/security-services",
        tags=["security-services"],
    )
if _svc_cfg.service_magnum_enabled:
    app.include_router(clusters_router, prefix="/api/clusters", tags=["clusters"])
if _svc_cfg.service_zun_enabled:
    app.include_router(containers_router, prefix="/api/containers", tags=["containers"])
if _svc_cfg.service_k3s_enabled:
    app.include_router(k3s_clusters_router, prefix="/api/k3s/clusters", tags=["k3s"])
    app.include_router(k3s_health_router, prefix="/api/k3s/clusters", tags=["k3s-health"])
    app.include_router(k3s_callback_router, prefix="/api/k3s", tags=["k3s-callback"])

# Union Mount 레이어 시스템 (DB 연결 시 항상 활성화)
from app.api.union import router as union_router  # noqa: E402

app.include_router(union_router, prefix="/api/union", tags=["union"])
if _svc_cfg.service_trove_enabled:
    from app.api.database.instances import router as trove_router

    app.include_router(trove_router, prefix="/api/database-instances", tags=["database"])
if _svc_cfg.service_swift_enabled:
    from app.api.object_storage.containers import router as swift_router
    from app.api.object_storage.upload import router as swift_upload_router

    app.include_router(swift_router, prefix="/api/object-storage", tags=["object-storage"])
    app.include_router(swift_upload_router)
if _svc_cfg.service_barbican_enabled:
    from app.api.secrets import containers_router, orders_router, secrets_router

    app.include_router(secrets_router, prefix="/api/secrets", tags=["secrets"])
    app.include_router(containers_router, prefix="/api/secret-containers", tags=["secret-containers"])
    app.include_router(orders_router, prefix="/api/secret-orders", tags=["secret-orders"])
    app.include_router(admin_secrets_router, prefix="/api/admin", tags=["admin-key-manager"])
# Common
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(metrics_router, prefix="/api/metrics", tags=["metrics"])
app.include_router(libraries_router, prefix="/api/libraries", tags=["libraries"])
app.include_router(sd_targets_router, prefix="/api/sd", tags=["sd-targets"])
app.include_router(grafana_auth_router, prefix="/api/grafana", tags=["grafana-auth"])
app.include_router(site_router, prefix="/api/site-config", tags=["site"])
app.include_router(user_dashboard_router, prefix="/api/user-dashboard", tags=["user-dashboard"])


@app.get("/api/health")
async def health():
    """K8s probe용. 항상 즉시 200 반환."""
    return {"status": "ok"}


@app.get("/api/health/detail")
async def health_detail(token_info: dict = Depends(get_token_info)):
    """모니터링 대시보드용 상세 헬스체크. Redis 연결 상태 포함."""
    detail: dict = {"status": "ok", "redis": "unknown"}
    try:
        from app.services.cache import _get_redis

        r = await _get_redis()
        await r.ping()
        detail["redis"] = "ok"
    except Exception:
        detail["redis"] = "unavailable"
    return detail


# ---------------------------------------------------------------------------
# 시계열 스냅샷 백그라운드 워커
# ---------------------------------------------------------------------------


async def _collect_snapshot() -> None:
    """관리자 자격으로 리소스 현황을 수집하여 Redis 시계열에 저장."""
    from app.config import get_settings
    from app.services import timeseries

    settings = get_settings()
    try:
        import openstack

        conn = openstack.connect(
            auth_url=settings.os_auth_url,
            username=settings.os_username,
            password=settings.os_password,
            project_name=settings.os_project_name,
            user_domain_name=settings.os_user_domain_name,
            project_domain_name=settings.os_project_domain_name,
            verify=settings.ssl_verify,
        )
    except Exception:
        _logger.warning("시계열 스냅샷: OpenStack 연결 실패", exc_info=True)
        return

    try:
        # 인스턴스 상태별 집계
        def _count_instances():
            counts: dict[str, int] = {
                "total": 0,
                "active": 0,
                "shutoff": 0,
                "error": 0,
                "shelved": 0,
                "other": 0,
            }
            for s in conn.compute.servers(all_projects=True, details=True):
                counts["total"] += 1
                st = (s.status or "").upper()
                if st == "ACTIVE":
                    counts["active"] += 1
                elif st == "SHUTOFF":
                    counts["shutoff"] += 1
                elif st == "ERROR":
                    counts["error"] += 1
                elif st in ("SHELVED", "SHELVED_OFFLOADED"):
                    counts["shelved"] += 1
                else:
                    counts["other"] += 1
            return counts

        def _count_volumes():
            counts: dict[str, int] = {
                "total": 0,
                "in_use": 0,
                "available": 0,
                "other": 0,
            }
            for v in conn.block_storage.volumes(all_projects=True):
                counts["total"] += 1
                st = (v.status or "").lower()
                if st == "in-use":
                    counts["in_use"] += 1
                elif st == "available":
                    counts["available"] += 1
                else:
                    counts["other"] += 1
            return counts

        def _count_file_storages():
            total = 0
            try:
                from app.services import manila

                file_storages = manila.list_file_storages(conn, all_tenants=True)
                total = len(file_storages)
            except Exception:
                pass
            return {"total": total}

        def _count_networks():
            nets = sum(1 for _ in conn.network.networks())
            routers = sum(1 for _ in conn.network.routers())
            fips_total = sum(1 for _ in conn.network.ips())
            fips_used = sum(1 for f in conn.network.ips() if f.port_id)
            return {
                "total": nets,
                "routers": routers,
                "floating_ips_total": fips_total,
                "floating_ips_used": fips_used,
            }

        async def _count_library_usage() -> dict[str, int]:
            """Nova metadata + union_user_mounts 기반 라이브러리/레이어 사용 카운트."""
            from sqlalchemy import text

            from app.database import get_session_factory

            counts: dict[str, int] = {}
            try:
                for s in conn.compute.servers(all_projects=True, details=True):
                    libs_str = (s.metadata or {}).get("union_libraries", "")
                    for lib in libs_str.split(","):
                        lib = lib.strip()
                        if lib:
                            key = f"lib:{lib}"
                            counts[key] = counts.get(key, 0) + 1
            except Exception:
                pass
            try:
                factory = get_session_factory()
                if factory:
                    async with factory() as db:
                        result = await db.execute(
                            text(
                                "SELECT ul.name, COUNT(*) as cnt FROM union_user_mounts uum "
                                "JOIN union_layers ul ON ul.id = uum.leaf_layer_id "
                                "WHERE uum.unmounted_at IS NULL GROUP BY ul.name"
                            )
                        )
                        for row in result:
                            key = f"layer:{row[0]}"
                            counts[key] = counts.get(key, 0) + int(row[1])
            except Exception:
                pass
            return counts

        inst_data = await asyncio.to_thread(_count_instances)
        vol_data = await asyncio.to_thread(_count_volumes)
        if settings.service_manila_enabled:
            file_storage_data = await asyncio.to_thread(_count_file_storages)
        else:
            file_storage_data = {"total": 0}
        net_data = await asyncio.to_thread(_count_networks)
        lib_usage_data = await _count_library_usage()

        await timeseries.record_snapshot("instances", inst_data)
        await timeseries.record_snapshot("volumes", vol_data)
        await timeseries.record_snapshot("file_storage", file_storage_data)
        await timeseries.record_snapshot("networks", net_data)
        await timeseries.record_snapshot("library_usage", lib_usage_data)

        _logger.info(
            "시계열 스냅샷 수집 완료: instances=%d volumes=%d file_storage=%d networks=%d library_keys=%d",
            inst_data["total"],
            vol_data["total"],
            file_storage_data["total"],
            net_data["total"],
            len(lib_usage_data),
        )
    except Exception:
        _logger.warning("시계열 스냅샷 수집 오류", exc_info=True)
    finally:
        try:
            await asyncio.to_thread(conn.close)
        except Exception:
            pass


async def _snapshot_loop() -> None:
    """10분 간격으로 시계열 스냅샷 수집."""
    # 시작 직후 첫 번째 수집
    await asyncio.sleep(30)
    while True:
        await _collect_snapshot()
        await asyncio.sleep(600)


async def _k3s_cleanup_loop() -> None:
    """5분 간격으로 stale CREATING 클러스터를 ERROR로 변경."""
    await asyncio.sleep(120)
    while True:
        try:
            from app.services import k3s_db as _k3s

            await _k3s.check_stale_clusters(timeout_minutes=30)
        except Exception:
            _logger.warning("k3s stale cluster check failed", exc_info=True)
        await asyncio.sleep(300)


async def _auto_backup_loop() -> None:
    """1시간 간격으로 자동 백업 설정이 있는 볼륨에 대해 백업 사이클 실행."""
    await asyncio.sleep(60)  # 시작 후 1분 대기
    while True:
        try:
            from app.services import auto_backup as _ab
            from app.services.keystone import get_admin_connection_for_project

            configs = await _ab.list_all_auto_backup_configs()
            if configs:
                _logger.info("auto_backup: %d개 볼륨 자동 백업 시작", len(configs))
                for cfg in configs:
                    project_id = cfg.get("project_id")
                    volume_id = cfg.get("volume_id")
                    if not project_id or not volume_id:
                        continue
                    try:
                        conn = await asyncio.to_thread(get_admin_connection_for_project, project_id)
                        await _ab.run_backup_cycle(conn, project_id, volume_id, cfg)
                    except Exception:
                        _logger.warning(
                            "auto_backup: 백업 사이클 실패 (volume=%s)",
                            volume_id,
                            exc_info=True,
                        )
        except Exception:
            _logger.warning("auto_backup: 루프 오류", exc_info=True)
        await asyncio.sleep(3600)  # 1시간


async def _deferred_create_tables() -> None:
    """DB 테이블 생성을 백그라운드에서 실행. API 기동을 차단하지 않는다."""
    from app.database import create_tables

    try:
        await create_tables()
    except Exception:
        _logger.warning(
            "DB 테이블 자동 생성 실패 (migrations/001_k3s_tables.sql 수동 실행 필요)",
            exc_info=True,
        )


@app.on_event("startup")
async def start_background_workers():
    # Redis 연결 pre-warm (첫 health check 지연 방지)
    try:
        from app.services.cache import _get_redis

        r = await _get_redis()
        await r.ping()
    except Exception:
        pass

    # DB 초기화 (database.url 설정 시)
    from app.database import init_db

    _db_cfg = _get_cfg()
    if _db_cfg.database_url:
        init_db(
            _db_cfg.database_url,
            pool_size=_db_cfg.database_pool_size,
            max_overflow=_db_cfg.database_max_overflow,
        )
        if _db_cfg.database_auto_create_tables:
            # create_tables()를 await하지 않고 백그라운드 태스크로 실행해
            # API가 DB DDL 완료를 기다리지 않고 즉시 요청을 받을 수 있게 한다.
            asyncio.create_task(_deferred_create_tables())

    asyncio.create_task(_snapshot_loop())
    asyncio.create_task(_auto_backup_loop())
    if _svc_cfg.service_k3s_enabled:
        asyncio.create_task(_k3s_cleanup_loop())

    from app.services.library_builder import _build_worker

    asyncio.create_task(_build_worker())


@app.on_event("shutdown")
async def shutdown_event():
    from app.database import close_db
    from app.services import prom_query

    await close_db()
    await prom_query.aclose_client()
