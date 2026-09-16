# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------
import logging
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
    from app.utils.daily_size_handler import DailySizeHandler
    from app.utils.log import SensitiveDataFilter

    cfg = get_settings()

    sensitive_filter = SensitiveDataFilter()
    formatter = _JSONFormatter()
    root = logging.getLogger()
    root.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(sensitive_filter)
    root.addHandler(stream_handler)

    try:
        file_handler = DailySizeHandler(
            log_directory=cfg.log_directory,
            max_bytes=cfg.log_max_bytes,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
        root.addHandler(file_handler)
    except OSError:
        pass  # 로그 디렉터리 생성/접근 불가 시 파일 핸들러 없이 진행

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
    announcements_router,
    dashboard_router,
    grafana_auth_router,
    libraries_router,
    metrics_router,
    sd_targets_router,
    site_router,
    tutorial_status_router,
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
from app.api.identity import admin_router, auth_router, gitlab_auth_router, mcp_access_router
from app.api.identity.admin_activity import router as admin_activity_router
from app.api.identity.admin_announcements import router as admin_announcements_router
from app.api.identity.admin_dashboard import router as admin_dashboard_router
from app.api.identity.admin_flavors import router as admin_flavors_router
from app.api.identity.admin_gpu import router as admin_gpu_router
from app.api.identity.admin_identity import router as admin_identity_router
from app.api.identity.admin_images import router as admin_images_router
from app.api.identity.admin_instances import router as admin_instances_router
from app.api.identity.admin_notion import router as admin_notion_router
from app.api.identity.admin_orphans import router as admin_orphans_router
from app.api.identity.admin_resource_policies import router as admin_resource_policies_router
from app.api.identity.admin_secrets import router as admin_secrets_router
from app.api.identity.admin_services import router as admin_services_router
from app.api.identity.admin_worker_runtime import router as admin_worker_runtime_router
from app.api.identity.invitations import router as invitations_router
from app.api.identity.profile import router as profile_router
from app.api.identity.profile_activity import router as profile_activity_router
from app.api.identity.projects import router as projects_router
from app.api.mcp import auth_router as mcp_oauth_router
from app.api.mcp import root_router as mcp_root_router
from app.api.mcp import router as mcp_router
from app.api.mcp_lumen import router as mcp_lumen_router
from app.api.union.layer_ops import router as admin_libraries_router
from app.api.union.layer_public import router as squashfs_libraries_router
from app.services.mcp_control_plane.transport import (
    install_mcp_route,
    mcp_paths,
    start_mcp_transport,
    stop_mcp_transport,
)

_mark("api.identity")

# ---------------------------------------------------------------------------
# Network and storage APIs
# ---------------------------------------------------------------------------
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
install_mcp_route(app)


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
        detail = exc.detail if getattr(exc, "_afterglow_safe_public_detail", False) else "내부 서버 오류"
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})
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


from app.services.activity import _audit_ctx
from app.services.activity import record as _record_activity


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """처리되지 않은 예외를 로그에 기록하고 500을 반환."""
    _logger.exception("Unhandled exception: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "내부 서버 오류"})


# 보안 응답 헤더: API 서버이므로 제한적 CSP 적용
# ---------------------------------------------------------------------------
# CRUD 자동 로깅: path prefix → resource_type allowlist 레지스트리
# ---------------------------------------------------------------------------
# 긴 prefix 를 먼저 두어 longest-prefix 매칭이 단순 순회로 동작하도록 정렬.
# 등록되지 않은 경로는 자동 로깅 제외 (allowlist 방식 — denylist 누락 위험 없음).
_AUDIT_PREFIX_MAP: list[tuple[str, str]] = [
    ("/api/v1/chat/admin/providers", "llm_provider"),
    ("/api/v1/chat/admin/title-model", "llm_model"),
    ("/api/v1/chat/admin/memory-model", "llm_model"),
    ("/api/v1/chat/admin/models", "llm_model"),
    ("/api/v1/chat/admin/mcp-servers", "chat_mcp_server"),
    ("/api/v1/chat/admin/custom-tools", "chat_custom_tool"),
    ("/api/v1/chat/code-workspaces", "chat_code_workspace"),
    ("/api/v1/chat/git-credentials", "chat_git_credential"),
    ("/api/v1/chat/agents", "chat_agent"),
    ("/api/v1/chat/workspaces", "chat_workspace"),
    ("/api/v1/chat/memories", "chat_memory"),
    ("/api/v1/chat/conversations", "chat_conversation"),
    ("/api/v1/chat/mcp-servers", "chat_mcp_server"),
    ("/api/v1/chat/custom-tools", "chat_custom_tool"),
    ("/api/v1/chat/api-keys", "chat_api_key"),
    ("/api/v1/chat/runs", "chat_run"),
    ("/api/v1/chat/assets", "chat_asset"),
    ("/api/v1/chat/temp-threads", "chat_temp_thread"),
    ("/api/v1/auth/mcp-oauth/grants", "mcp_grant"),
    ("/api/v1/auth/mcp-tokens", "mcp_grant"),
    ("/api/v1/volumes/backups", "volume_backup"),
    ("/api/v1/admin/announcements", "announcement"),
    ("/api/v1/volume-snapshots", "volume_snapshot"),
    ("/api/v1/share-snapshots", "share_snapshot"),
    ("/api/v1/share-networks", "share_network"),
    ("/api/v1/security-services", "security_service"),
    ("/api/v1/security-groups", "security_group"),
    ("/api/v1/secret-containers", "secret_container"),
    ("/api/v1/secret-orders", "secret_order"),
    ("/api/v1/database-instances", "database"),
    ("/api/v1/admin/worker-runtime", "worker_runtime"),
    ("/api/v1/admin/resource-policies", "resource_policy"),
    ("/api/v1/admin/libraries", "union_layer"),
    ("/api/v1/libraries/squashfs", "union_layer"),
    ("/api/v1/admin/palimpsest", "palimpsest_layer"),
    ("/api/v1/palimpsest", "palimpsest_layer"),
    ("/api/v1/admin/images", "image"),
    ("/api/v1/admin/projects", "project"),
    ("/api/v1/waygate/servers", "waygate_server"),
    ("/api/v1/loadbalancers", "load_balancer"),
    ("/api/v1/k3s/clusters", "container_cluster"),
    ("/api/v1/file-storage", "file_storage"),
    ("/api/v1/object-storage", "object_storage"),
    ("/api/v1/invitations", "invitation"),
    ("/api/v1/instances/cloud-init", "cloud_init_snippet"),
    ("/api/v1/instances", "instance"),
    ("/api/v1/keypairs", "keypair"),
    ("/api/v1/networks", "network"),
    ("/api/v1/containers", "container"),
    ("/api/v1/libraries", "library"),
    ("/api/v1/volumes", "volume"),
    ("/api/v1/routers", "router"),
    ("/api/v1/secrets", "secret"),
    ("/api/v1/images", "image"),
    ("/api/v1/clusters", "container_cluster"),
]


def _resource_for_path(path: str) -> tuple[str, str | None] | None:
    """path prefix longest-match → (resource_type, resource_id) 또는 None(제외).

    resource_id: prefix 제거 후 첫 path 세그먼트가 존재하면 사용, 없으면 None.
    """
    for prefix, rtype in _AUDIT_PREFIX_MAP:
        if path.startswith(prefix):
            rest = path[len(prefix) :].lstrip("/")
            rid = rest.split("/")[0] if rest else None
            return (rtype, rid or None)
    return None


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
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
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
    if not request.url.path.startswith(("/api/v1/health", "/api/health")):
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


_CORS_ALLOW_HEADERS = "Content-Type, X-Project-Id, Authorization, Idempotency-Key, Last-Event-ID"
_CORS_ALLOW_METHODS = "GET, POST, PUT, DELETE, OPTIONS, PATCH"


def _is_mcp_no_cors_path(path: str) -> bool:
    return any(path == resource_path or path.startswith(f"{resource_path}/oauth/") for resource_path in mcp_paths())


def _get_allowed_origins() -> set[str]:
    from app.config import get_settings

    return set(get_settings().cors_origin_list)


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin", "")
    if _is_mcp_no_cors_path(request.url.path):
        return await call_next(request)
    if request.method == "OPTIONS":
        if origin not in _get_allowed_origins():
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

    response = await call_next(request)
    if origin and origin in _get_allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = _CORS_ALLOW_METHODS
        response.headers["Access-Control-Allow-Headers"] = _CORS_ALLOW_HEADERS
        response.headers["Vary"] = "Origin"
    return response


@app.middleware("http")
async def activity_audit_middleware(request: Request, call_next):
    """mutation(POST/PUT/PATCH/DELETE) 성공 시 명시적 로그가 없으면 자동 1행 기록.

    수동 rec()/record() 호출이 있으면 _audit_ctx 공유 dict 를 통해 신호를 수신하고
    자동 로깅을 건너뛴다 (중복 방지). 기존 218개 수동 호출은 그대로 유지.
    """
    is_mut = request.method in ("POST", "PUT", "PATCH", "DELETE")
    holder: dict = {"logged": False}
    tok = _audit_ctx.set(holder) if is_mut else None
    try:
        response = await call_next(request)
    finally:
        if tok is not None:
            _audit_ctx.reset(tok)

    if is_mut and not holder["logged"] and 200 <= response.status_code < 300:
        info = getattr(request.state, "token_info", None)
        mapped = _resource_for_path(request.url.path)
        if info and mapped:
            rtype, rid = mapped
            pid = info.get("project_id", "")
            uid = info.get("user_id", "")
            uname = info.get("username", "")
            if pid and uid:
                action = {
                    "POST": "create",
                    "PUT": "update",
                    "PATCH": "update",
                    "DELETE": "delete",
                }[request.method]
                try:
                    await _record_activity(
                        project_id=pid,
                        user_id=uid,
                        username=uname,
                        resource_type=rtype,
                        action=action,
                        status="success",
                        resource_id=rid,
                    )
                except Exception:
                    pass  # best-effort: 응답을 차단하지 않는다

    return response


# Identity
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(mcp_access_router, prefix="/api/v1/auth", tags=["mcp-access"])
app.include_router(mcp_router, prefix="/api/v1/mcp", tags=["mcp"])
app.include_router(mcp_lumen_router, prefix="/api/v1/mcp/lumen", tags=["mcp-lumen"])
app.include_router(mcp_root_router, tags=["mcp"])
app.include_router(mcp_oauth_router, prefix="/api/v1/auth", tags=["mcp-oauth"])
# OIDC/OAuth API routes follow the project-wide /api/v1 mount rule.
app.include_router(gitlab_auth_router, prefix="/api/v1/auth", tags=["auth-oidc"])
# admin_instances_router를 admin_router보다 먼저 등록 (정적 경로 /instances/async 우선 매칭)
app.include_router(admin_instances_router, prefix="/api/v1/admin", tags=["admin-instances"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(admin_services_router, prefix="/api/v1/admin", tags=["admin-services"])
app.include_router(admin_worker_runtime_router, prefix="/api/v1/admin", tags=["admin-worker-runtime"])
app.include_router(admin_flavors_router, prefix="/api/v1/admin", tags=["admin-flavors"])
app.include_router(admin_identity_router, prefix="/api/v1/admin", tags=["admin-identity"])
app.include_router(admin_gpu_router, prefix="/api/v1/admin", tags=["admin-gpu"])
app.include_router(admin_libraries_router, prefix="/api/v1/admin/libraries", tags=["admin-libraries"])
app.include_router(admin_notion_router, prefix="/api/v1/admin", tags=["admin-notion"])
app.include_router(admin_images_router, prefix="/api/v1/admin", tags=["admin-images"])
app.include_router(admin_resource_policies_router, prefix="/api/v1/admin", tags=["admin-resource-policies"])
app.include_router(profile_router, prefix="/api/v1/profile", tags=["profile"])
app.include_router(profile_activity_router, prefix="/api/v1/profile/activity", tags=["profile-activity"])
app.include_router(admin_activity_router, prefix="/api/v1/admin", tags=["admin-activity"])
app.include_router(admin_orphans_router, prefix="/api/v1/admin", tags=["admin-orphans"])
app.include_router(admin_dashboard_router, prefix="/api/v1/admin", tags=["admin-dashboard"])
app.include_router(admin_announcements_router, prefix="/api/v1/admin/announcements", tags=["admin-announcements"])
app.include_router(projects_router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(invitations_router, prefix="/api/v1/invitations", tags=["invitations"])
# Compute
app.include_router(images_router, prefix="/api/v1/images", tags=["images"])
app.include_router(flavors_router, prefix="/api/v1/flavors", tags=["flavors"])
# instance_health_router을 instances_router보다 먼저 등록 (/health 경로 충돌 방지)
app.include_router(instance_health_router, prefix="/api/v1/instances", tags=["instance-health"])
# 레거시 /api/instances 유지 — cloud-init baked VM 호환 (health/report, rotate-cephx)
app.include_router(instance_health_router, prefix="/api/instances", tags=["instance-health"], include_in_schema=False)
app.include_router(instance_metrics_router, prefix="/api/v1/instances", tags=["instance-metrics"])
app.include_router(instances_router, prefix="/api/v1/instances", tags=["instances"])
app.include_router(keypairs_router, prefix="/api/v1/keypairs", tags=["keypairs"])
# Storage (backups 먼저 등록 — /api/volumes/{id} catch-all 보다 앞에)
app.include_router(volume_backups_router, prefix="/api/v1/volumes/backups", tags=["volume-backups"])
app.include_router(volume_snapshots_router, prefix="/api/v1/volume-snapshots", tags=["volume-snapshots"])
app.include_router(volumes_router, prefix="/api/v1/volumes", tags=["volumes"])
# Network
app.include_router(networks_router, prefix="/api/v1/networks", tags=["networks"])
app.include_router(routers_router, prefix="/api/v1/routers", tags=["routers"])
app.include_router(loadbalancers_router, prefix="/api/v1/loadbalancers", tags=["loadbalancers"])
app.include_router(security_groups_router, prefix="/api/v1/security-groups", tags=["security-groups"])
# Optional services — afterglow.conf [services] 섹션에서 활성화
from app.config import get_settings as _get_cfg

_svc_cfg = _get_cfg()
if _svc_cfg.service_manila_enabled:
    app.include_router(file_storage_router, prefix="/api/v1/file-storage", tags=["file-storage"])
    app.include_router(share_snapshots_router, prefix="/api/v1/share-snapshots", tags=["share-snapshots"])
    app.include_router(share_networks_router, prefix="/api/v1/share-networks", tags=["share-networks"])
    app.include_router(
        security_services_router,
        prefix="/api/v1/security-services",
        tags=["security-services"],
    )
if _svc_cfg.service_magnum_enabled:
    app.include_router(clusters_router, prefix="/api/v1/clusters", tags=["clusters"])
if _svc_cfg.service_zun_enabled:
    app.include_router(containers_router, prefix="/api/v1/containers", tags=["containers"])
if _svc_cfg.service_k3s_enabled:
    from app.api.drover import drover_admin_router, drover_callback_router, drover_proxy_router
    from app.api.internal_k3s import router as internal_k3s_router
    from app.api.k3s_shell_proxy import router as k3s_shell_proxy_router

    # Internal endpoints and baked machine callbacks precede the authenticated catch-all proxy.
    app.include_router(internal_k3s_router, prefix="/api/v1/internal/k3s", tags=["internal-k3s"])
    app.include_router(drover_callback_router, prefix="/api/v1/k3s", tags=["k3s-callback"])
    app.include_router(
        drover_callback_router,
        prefix="/api/k3s",
        tags=["k3s-callback"],
        include_in_schema=False,
    )
    app.include_router(k3s_shell_proxy_router, prefix="/api/v1/k3s/clusters", tags=["k3s-shell"])
    app.include_router(drover_proxy_router, prefix="/api/v1/k3s", tags=["k3s"])
    app.include_router(drover_admin_router, prefix="/api/v1/admin", tags=["admin-k3s"])

# Palimpsest (레이어드 VM) — docs/palimpsest.md
#
# 2세대 union 표면(`/api/v1/union`)은 폐기됐다 — 인프라(중앙 Manila share, CephX keyring,
# Builder VM)가 배포된 적이 없고 프론트 호출자도 nav 에서 도달 불가능한 고립 페이지뿐이었다.
# `union_layers`/`union_templates`/`union_user_mounts` 테이블은 데이터 보존을 위해 남긴다.
from app.api.palimpsest import (  # noqa: E402
    palimpsest_admin_router,
    palimpsest_builds_router,
    palimpsest_hub_router,
    palimpsest_layers_router,
)

app.include_router(palimpsest_layers_router, prefix="/api/v1/palimpsest", tags=["palimpsest"])
app.include_router(palimpsest_hub_router, prefix="/api/v1/palimpsest/hub", tags=["palimpsest-hub"])
app.include_router(palimpsest_builds_router, prefix="/api/v1/palimpsest/builds", tags=["palimpsest-builds"])
app.include_router(palimpsest_admin_router, prefix="/api/v1/admin/palimpsest", tags=["palimpsest-admin"])
if _svc_cfg.service_trove_enabled:
    from app.api.database.instances import router as trove_router

    app.include_router(trove_router, prefix="/api/v1/database-instances", tags=["database"])
if _svc_cfg.service_swift_enabled:
    from app.api.object_storage.containers import router as swift_router
    from app.api.object_storage.upload import router as swift_upload_router

    app.include_router(swift_router, prefix="/api/v1/object-storage", tags=["object-storage"])
    app.include_router(swift_upload_router, prefix="/api/v1/object-storage", tags=["object-storage-upload"])
if _svc_cfg.service_barbican_enabled:
    from app.api.secrets import containers_router, orders_router, secrets_router

    app.include_router(secrets_router, prefix="/api/v1/secrets", tags=["secrets"])
    app.include_router(containers_router, prefix="/api/v1/secret-containers", tags=["secret-containers"])
    app.include_router(orders_router, prefix="/api/v1/secret-orders", tags=["secret-orders"])
    app.include_router(admin_secrets_router, prefix="/api/v1/admin", tags=["admin-key-manager"])
if _svc_cfg.service_waygate_enabled:
    from app.api.waygate import waygate_agent_router, waygate_proxy_router

    # Agent routes precede the catch-all proxy because their bearer token is not a browser/Keystone token.
    app.include_router(waygate_agent_router, prefix="/api/v1/waygate/servers", tags=["waygate-agent"])
    app.include_router(waygate_proxy_router, prefix="/api/v1/waygate", tags=["waygate"])
from app.api.lumen import register_lumen

register_lumen(app, _svc_cfg)
# Common
app.include_router(announcements_router, prefix="/api/v1/announcements", tags=["announcements"])
app.include_router(tutorial_status_router, prefix="/api/v1/tutorials", tags=["tutorials"])
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(metrics_router, prefix="/api/v1/metrics", tags=["metrics"])
app.include_router(squashfs_libraries_router, prefix="/api/v1/libraries/squashfs", tags=["squashfs-libraries"])
app.include_router(libraries_router, prefix="/api/v1/libraries", tags=["libraries"])
app.include_router(sd_targets_router, prefix="/api/v1/sd", tags=["sd-targets"])
app.include_router(grafana_auth_router, prefix="/api/v1/grafana", tags=["grafana-auth"])
app.include_router(site_router, prefix="/api/v1/site-config", tags=["site"])
app.include_router(user_dashboard_router, prefix="/api/v1/user-dashboard", tags=["user-dashboard"])


@app.get("/api/v1/health")
@app.get("/api/health", include_in_schema=False)
async def health():
    """K8s probe용. 항상 즉시 200 반환."""
    return {"status": "ok"}


@app.get("/api/v1/health/detail")
@app.get("/api/health/detail", include_in_schema=False)
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
                        # Palimpsest 활성 레이어 소비 집계.
                        # 이전에는 2세대 `union_user_mounts` 를 세었으나 그 테이블은 채워진 적이
                        # 없다(인프라 미배포) — 실제 사용 중인 스택은 `layer_consumes` 다.
                        result = await db.execute(
                            text(
                                "SELECT profile_name, COUNT(*) AS cnt FROM layer_consumes "
                                "WHERE status = 'active' AND server_id IS NOT NULL "
                                "GROUP BY profile_name"
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


async def _mcp_cleanup_loop() -> None:
    """Sweep expired delegated-authority state; Keystone cleanup stays owner-scoped."""
    await asyncio.sleep(60)
    while True:
        try:
            from app.database import get_session_factory
            from app.services.mcp_control_plane.cleanup import sweep_delegated_authority

            session_factory = get_session_factory()
            if session_factory is not None:
                await sweep_delegated_authority(session_factory)
        except Exception:
            _logger.warning("MCP delegated-authority cleanup failed", exc_info=True)
        await asyncio.sleep(300)


async def _trash_cleanup_loop() -> None:
    """1시간 간격으로 만료된 휴지통 오브젝트·버킷을 영구 삭제.

    오브젝트 휴지통: 각 프로젝트의 모든 *-trash 버킷에서 retention_days 경과 항목 삭제.
    버킷 휴지통: Redis sorted-set에서 만료된 소프트 삭제 컨테이너를 하드 삭제.
    """
    await asyncio.sleep(180)  # 시작 후 3분 대기
    while True:
        try:
            import time as _time

            from app.api.object_storage.containers import (
                _get_deleted_containers,
                _mark_container_deleted,
                _unmark_container_deleted,
            )
            from app.config import get_settings
            from app.services import swift
            from app.services.keystone import (
                get_admin_connection_for_project,
                list_all_project_ids,
            )

            settings = get_settings()
            retention_days = settings.os_trash_retention_days
            cutoff = int(_time.time()) - retention_days * 86400

            try:
                project_ids: set[str] = await asyncio.to_thread(list_all_project_ids)
            except Exception:
                _logger.warning("trash_cleanup: 프로젝트 목록 조회 실패", exc_info=True)
                project_ids = set()

            for pid in project_ids:
                if not pid:
                    continue
                try:
                    conn = await asyncio.to_thread(get_admin_connection_for_project, pid)
                except Exception:
                    _logger.debug("trash_cleanup: 프로젝트 %s 연결 실패", pid, exc_info=True)
                    continue

                try:
                    # 컨테이너 목록 조회 (step 1·reconcile 공유)
                    all_containers: list = []
                    try:
                        all_containers = await asyncio.to_thread(swift.list_containers, conn, False, True)
                    except Exception:
                        _logger.debug("trash_cleanup: pid=%s 컨테이너 목록 조회 실패", pid, exc_info=True)

                    # 1. 오브젝트 휴지통 — 모든 *-trash 버킷의 만료 항목 삭제
                    try:
                        trash_containers = [c for c in all_containers if c.get("is_trash")]
                        for tc in trash_containers:
                            # 원본 버킷 이름 추출 (suffix "-trash" 제거)
                            origin = tc["name"][: -len(swift.TRASH_SUFFIX)]
                            trash_count = tc.get("count", -1)
                            # C-2: 이미 빈 trash 버킷은 즉시 정리
                            if trash_count == 0:
                                try:
                                    await asyncio.to_thread(swift.delete_container, conn, tc["name"])
                                    _logger.info(
                                        "trash_cleanup: 빈 휴지통 버킷 삭제 pid=%s bucket=%s",
                                        pid,
                                        tc["name"],
                                    )
                                except Exception:
                                    _logger.debug(
                                        "trash_cleanup: 빈 휴지통 버킷 삭제 실패 pid=%s bucket=%s",
                                        pid,
                                        tc["name"],
                                        exc_info=True,
                                    )
                                continue
                            try:
                                result = await asyncio.to_thread(
                                    swift.purge_expired_trash_objects, conn, origin, retention_days
                                )
                                if result["purged"]:
                                    _logger.info(
                                        "trash_cleanup: pid=%s bucket=%s purged=%d",
                                        pid,
                                        origin,
                                        len(result["purged"]),
                                    )
                                # C-2: purge 후 trash 버킷이 비었으면 삭제
                                if trash_count >= 0 and len(result.get("purged", [])) >= trash_count:
                                    try:
                                        await asyncio.to_thread(swift.delete_container, conn, tc["name"])
                                        _logger.info(
                                            "trash_cleanup: 빈 휴지통 버킷 삭제 pid=%s bucket=%s",
                                            pid,
                                            tc["name"],
                                        )
                                    except Exception:
                                        _logger.debug(
                                            "trash_cleanup: 빈 휴지통 버킷 삭제 실패 pid=%s bucket=%s",
                                            pid,
                                            tc["name"],
                                            exc_info=True,
                                        )
                            except Exception:
                                _logger.debug(
                                    "trash_cleanup: 오브젝트 purge 실패 pid=%s bucket=%s",
                                    pid,
                                    origin,
                                    exc_info=True,
                                )
                    except Exception:
                        _logger.debug("trash_cleanup: pid=%s 오브젝트 휴지통 처리 실패", pid, exc_info=True)

                    # C-1. Redis 재동기화 — Swift 메타에 있으나 Redis 누락된 소프트 삭제 버킷 복원
                    # Redis 유실 시 소프트 삭제 버킷이 사용자 목록에 부활하는 것을 ≤1h 내 자동 교정한다.
                    try:
                        current_redis_map = await _get_deleted_containers(pid)
                        normal_containers = [
                            c for c in all_containers if not c.get("is_trash") and not c.get("is_quarantine")
                        ]
                        reconciled = 0
                        for nc in normal_containers:
                            cname = nc["name"]
                            if cname in current_redis_map:
                                continue  # 이미 Redis에 있음
                            try:
                                meta_epoch = await asyncio.to_thread(swift.get_container_deleted_at, conn, cname)
                            except Exception:
                                continue
                            if meta_epoch is not None:
                                await _mark_container_deleted(pid, cname, meta_epoch, retention_days)
                                reconciled += 1
                                _logger.info(
                                    "trash_cleanup: Redis 재동기화 pid=%s name=%s epoch=%d",
                                    pid,
                                    cname,
                                    meta_epoch,
                                )
                        if reconciled:
                            _logger.info(
                                "trash_cleanup: reconcile 완료 pid=%s count=%d",
                                pid,
                                reconciled,
                            )
                    except Exception:
                        _logger.debug("trash_cleanup: pid=%s reconcile 실패", pid, exc_info=True)

                    # 2. 버킷 휴지통 — 만료된 소프트 삭제 컨테이너 하드 삭제 (reconcile 후 재조회)
                    try:
                        deleted_map = await _get_deleted_containers(pid)
                        for cname, epoch in deleted_map.items():
                            if epoch <= cutoff:
                                try:
                                    await asyncio.to_thread(swift.delete_container, conn, cname)
                                    _logger.info("trash_cleanup: 버킷 영구 삭제 pid=%s name=%s", pid, cname)
                                except Exception:
                                    _logger.debug(
                                        "trash_cleanup: 버킷 삭제 실패 pid=%s name=%s", pid, cname, exc_info=True
                                    )
                                finally:
                                    await _unmark_container_deleted(pid, cname)
                    except Exception:
                        _logger.debug("trash_cleanup: pid=%s 버킷 휴지통 처리 실패", pid, exc_info=True)

                finally:
                    import contextlib as _cl

                    with _cl.suppress(Exception):
                        await asyncio.to_thread(conn.close)

        except Exception:
            _logger.warning("trash_cleanup: 루프 오류", exc_info=True)
        await asyncio.sleep(3600)  # 1시간


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
    await _deferred_load_gpu_catalog()


async def _deferred_load_gpu_catalog() -> None:
    """DB의 GPU 장치 카탈로그를 PCI_DEVICE_MAP에 overlay. 실패해도 base map으로 동작.

    다중 replica 환경에서 각 pod가 startup 시 DB 카탈로그를 반드시 로드해야 한다.
    이전 구현은 `is_db_available()`가 처음에 False면 즉시 return하고 재시도하지 않아,
    DB 준비가 늦으면 해당 pod의 PCI_DEVICE_MAP에 DB overlay가 영구 누락되어
    하이퍼바이저 GPU 이름이 raw로 표시되는 문제가 있었다. 짧게 재시도한다.
    """
    from app.database import is_db_available
    from app.services.gpu_catalog import refresh_device_map_from_db

    for attempt in range(8):
        if is_db_available():
            try:
                await refresh_device_map_from_db()
                return
            except Exception:
                _logger.warning("GPU 장치 카탈로그 DB 로드 실패 (시도 %d) — 재시도", attempt + 1, exc_info=True)
        await asyncio.sleep(min(2**attempt, 30))
    _logger.warning("GPU 장치 카탈로그 DB 로드 최종 실패 — 내장/config 카탈로그로 동작")


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
            connect_timeout=_db_cfg.database_connect_timeout,
            pool_timeout=_db_cfg.database_pool_timeout,
            unhealthy_seconds=_db_cfg.database_unhealthy_seconds,
        )
        if _db_cfg.database_auto_create_tables:
            # create_tables()를 await하지 않고 백그라운드 태스크로 실행해
            # API가 DB DDL 완료를 기다리지 않고 즉시 요청을 받을 수 있게 한다.
            asyncio.create_task(_deferred_create_tables())
        else:
            asyncio.create_task(_deferred_load_gpu_catalog())

    asyncio.create_task(_snapshot_loop())
    asyncio.create_task(_auto_backup_loop())
    if _svc_cfg.service_swift_enabled:
        asyncio.create_task(_trash_cleanup_loop())
    if _svc_cfg.service_mcp_enabled:
        await start_mcp_transport()
        asyncio.create_task(_mcp_cleanup_loop())

    if _db_cfg.worker_runtime_mode != "static" and _db_cfg.worker_runtime_reconcile_interval > 0:
        from app.services.worker_runtime import reconcile_loop

        asyncio.create_task(reconcile_loop())

    from app.services.library_builder import _build_worker, reconcile_orphan_builds

    asyncio.create_task(reconcile_orphan_builds())
    asyncio.create_task(_build_worker())


@app.on_event("shutdown")
async def shutdown_event():
    from app.database import close_db
    from app.services import prom_query

    await stop_mcp_transport()
    await close_db()
    await prom_query.aclose_client()
