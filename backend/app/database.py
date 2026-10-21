"""SQLAlchemy async 데이터베이스 연결 관리.

설정: afterglow.conf [database] 섹션 또는 DATABASE_URL 환경변수.
url이 비어있으면 DB 연결 없이 Redis 폴백으로 동작.
"""

import logging
import sys
import time
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

_logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None

# circuit breaker: OperationalError 발생 시 일정 시간 DB 호출 차단
_db_unhealthy_until: float = 0.0
_default_unhealthy_seconds: int = 15


class Base(DeclarativeBase):
    pass


def init_db(
    database_url: str,
    pool_size: int = 5,
    max_overflow: int = 10,
    connect_timeout: int = 10,
    pool_timeout: int = 10,
    unhealthy_seconds: int = 15,
) -> None:
    """앱 시작 시 호출. engine과 session factory를 초기화."""
    global _engine, _session_factory, _default_unhealthy_seconds
    _default_unhealthy_seconds = unhealthy_seconds
    if not database_url:
        _logger.info("database.url 미설정 — DB 없이 Redis 폴백으로 동작합니다")
        return

    _engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_timeout=pool_timeout,
        pool_recycle=1800,
        connect_args={"connect_timeout": connect_timeout},
        echo=False,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    _logger.info("데이터베이스 연결 초기화 완료: %s", _mask_url(database_url))


def is_db_available() -> bool:
    """DB 연결이 초기화되어 있고 circuit breaker가 열리지 않았으면 True."""
    if _engine is None:
        return False
    if time.time() < _db_unhealthy_until:
        return False
    return True


def is_db_configured() -> bool:
    """Return whether this process has a configured database engine.

    Unlike ``is_db_available``, this deliberately ignores the temporary
    unhealthy circuit state so callers can fail closed rather than silently
    falling back to an unrelated storage backend.
    """
    return _engine is not None


_CONNECTION_ERROR_CODES = frozenset({2003, 2006, 2013, 2014, 2055})


def is_connection_error(error: BaseException | None) -> bool:
    """Return True only for DBAPI transport/protocol failures.

    Query/schema failures such as MySQL 1054 must fail that request without
    opening the process-wide availability breaker.
    """
    if error is None:
        return False
    current: BaseException | None = error
    while current is not None:
        args = getattr(current, "args", ())
        if args and isinstance(args[0], int) and args[0] in _CONNECTION_ERROR_CODES:
            return True
        current = getattr(current, "orig", None) or getattr(current, "__cause__", None)
    return False


def mark_db_unhealthy(error: BaseException | None = None, seconds: int | None = None) -> bool:
    """Open the breaker only for confirmed database connection failures.

    When called from an exception handler, ``sys.exception()`` supplies the
    caught DBAPI error so legacy call sites remain safe during the cutover.
    """
    error = error if error is not None else sys.exception()
    if not is_connection_error(error):
        _logger.info("DB query failure did not open circuit breaker", exc_info=error is not None)
        return False
    global _db_unhealthy_until
    duration = seconds if seconds is not None else _default_unhealthy_seconds
    _db_unhealthy_until = time.time() + duration
    _logger.warning("DB circuit breaker 활성화: %d초 동안 DB 호출 차단", duration)
    return True


async def create_tables() -> None:
    """ORM 모델 기반으로 테이블 자동 생성 (auto_create_tables=true 시 호출)."""
    if _engine is None:
        return
    from app.models.account_spaces import PersonalProjectIntent, SharedDomainIntent  # noqa: F401
    from app.models.db import Base as _ModelBase  # noqa: F401 — side effect: 모델 등록
    from app.models.organization_provisioning import OrganizationBinding  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(_ModelBase.metadata.create_all)

    # 기존 테이블에 soft-delete 컬럼 추가 (없는 경우에만)
    async with _engine.begin() as conn:
        # 프로젝트 기본 네트워크 테이블 생성 (없는 경우에만)
        try:
            await conn.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS project_default_networks ("
                "id INT AUTO_INCREMENT PRIMARY KEY,"
                "project_id VARCHAR(64) NOT NULL,"
                "network_id VARCHAR(64) NOT NULL,"
                "subnet_id VARCHAR(64) DEFAULT NULL,"
                "router_id VARCHAR(64) DEFAULT NULL,"
                "auto_created BOOLEAN NOT NULL DEFAULT TRUE,"
                "created_at DATETIME(6) NOT NULL,"
                "updated_at DATETIME(6) DEFAULT NULL,"
                "UNIQUE KEY uq_project_default_networks_project_id (project_id),"
                "KEY ix_project_default_networks_project_id (project_id)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
        except Exception:
            pass  # 이미 존재하면 무시

        # (폐기) 2세대 union 테이블 DDL — union_layers / union_templates / union_user_mounts.
        # Palimpsest 통합 시 ORM·API 와 함께 제거했다. 신규 배포는 이 테이블을 만들지 않고,
        # 기존 배포의 테이블은 데이터 보존을 위해 그대로 둔다(DROP 마이그레이션 없음).
        # 레이어 정체성은 이제 layer_artifacts.blob_digest 다 — docs/palimpsest.md §3.

        # library_builds 에 ephemeral 빌드 컬럼 추가 (없는 경우에만)
        for _col_sql in [
            "ALTER TABLE library_builds ADD COLUMN recipe_id INT DEFAULT NULL",
            "ALTER TABLE library_builds ADD COLUMN port_id VARCHAR(64) DEFAULT NULL",
            "ALTER TABLE library_builds ADD COLUMN build_token CHAR(32) DEFAULT NULL",
            "ALTER TABLE library_builds ADD UNIQUE KEY uq_library_builds_token (build_token)",
            "ALTER TABLE library_builds ADD COLUMN console_log_excerpt TEXT DEFAULT NULL",
            "ALTER TABLE library_builds ADD COLUMN cloud_init_status VARCHAR(20) DEFAULT NULL",
        ]:
            try:
                await conn.exec_driver_sql(_col_sql)
            except Exception:
                pass  # 이미 존재하면 무시

        # admin squashfs layer workflow metadata columns (019/020, 없는 경우에만)
        for _col_sql in [
            "ALTER TABLE layer_builds ADD COLUMN apt_packages JSON NULL AFTER pip_packages",
            ("ALTER TABLE layer_artifacts ADD COLUMN apt_packages JSON NULL AFTER pip_packages"),
            (
                "ALTER TABLE layer_builds ADD COLUMN ubuntu_base VARCHAR(255) NOT NULL "
                "DEFAULT 'ubuntu-24.04-server-2026-04-15' AFTER apt_packages"
            ),
            (
                "ALTER TABLE layer_artifacts ADD COLUMN ubuntu_base VARCHAR(255) NOT NULL "
                "DEFAULT 'ubuntu-24.04-server-2026-04-15' AFTER apt_packages"
            ),
        ]:
            try:
                await conn.exec_driver_sql(_col_sql)
            except Exception:
                pass  # 이미 존재하면 무시

        # Glance base image fingerprints + Dockerfile import jobs (021, 없는 경우에만)
        for _table in ("layer_builds", "layer_artifacts"):
            for _col, _def in [
                ("base_image_id", "VARCHAR(128) DEFAULT NULL"),
                ("base_image_name", "VARCHAR(255) DEFAULT NULL"),
                ("base_image_checksum", "VARCHAR(128) DEFAULT NULL"),
                ("base_image_os_hash_algo", "VARCHAR(32) DEFAULT NULL"),
                ("base_image_os_hash_value", "VARCHAR(128) DEFAULT NULL"),
                ("base_image_min_disk", "INT DEFAULT NULL"),
                ("base_image_visibility", "VARCHAR(32) DEFAULT NULL"),
                ("base_image_owner", "VARCHAR(128) DEFAULT NULL"),
                ("source_metadata", "JSON DEFAULT NULL"),
            ]:
                try:
                    await conn.exec_driver_sql(f"ALTER TABLE {_table} ADD COLUMN {_col} {_def}")
                except Exception:
                    pass  # 이미 존재하면 무시

        # Public squashfs publication and caller-owned consume tracking (022, 없는 경우에만)
        for _col_sql in [
            "ALTER TABLE layer_consumes ADD COLUMN project_id VARCHAR(64) DEFAULT NULL",
            "ALTER TABLE layer_consumes ADD COLUMN artifact_ids JSON DEFAULT NULL",
            "ALTER TABLE layer_consumes ADD INDEX ix_layer_consumes_project_id (project_id)",
            "ALTER TABLE layer_artifacts ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE layer_artifacts ADD INDEX ix_layer_artifacts_is_published (is_published)",
            "ALTER TABLE layer_profiles ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE layer_profiles ADD INDEX ix_layer_profiles_is_published (is_published)",
        ]:
            try:
                await conn.exec_driver_sql(_col_sql)
            except Exception:
                pass  # 이미 존재하면 무시
        try:
            await conn.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS layer_import_jobs ("
                "id INT AUTO_INCREMENT PRIMARY KEY,"
                "source_type VARCHAR(32) NOT NULL DEFAULT 'github_dockerfile',"
                "status VARCHAR(32) NOT NULL DEFAULT 'queued',"
                "progress_step VARCHAR(64) DEFAULT NULL,"
                "progress_pct INT NOT NULL DEFAULT 0,"
                "error_message TEXT DEFAULT NULL,"
                "github_url VARCHAR(512) NOT NULL,"
                "repo_owner VARCHAR(64) NOT NULL,"
                "repo_name VARCHAR(128) NOT NULL,"
                "commit_sha CHAR(40) NOT NULL,"
                "dockerfile_path VARCHAR(255) NOT NULL DEFAULT 'Dockerfile',"
                "layer_prefix VARCHAR(64) NOT NULL,"
                "profile_name VARCHAR(64) NOT NULL,"
                "ubuntu_base VARCHAR(255) NOT NULL,"
                "base_image_id VARCHAR(128) NOT NULL,"
                "base_image_name VARCHAR(255) DEFAULT NULL,"
                "base_image_checksum VARCHAR(128) DEFAULT NULL,"
                "base_image_os_hash_algo VARCHAR(32) DEFAULT NULL,"
                "base_image_os_hash_value VARCHAR(128) DEFAULT NULL,"
                "base_image_min_disk INT DEFAULT NULL,"
                "planned_layers JSON DEFAULT NULL,"
                "artifact_ids JSON DEFAULT NULL,"
                "build_ids JSON DEFAULT NULL,"
                "created_at DATETIME(6) NOT NULL,"
                "updated_at DATETIME(6) NOT NULL,"
                "completed_at DATETIME(6) DEFAULT NULL,"
                "KEY ix_layer_import_jobs_status (status),"
                "KEY ix_layer_import_jobs_created_at (created_at)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
        except Exception:
            pass

        for _col, _def in [
            ("source_type", "VARCHAR(32) NOT NULL DEFAULT 'github_dockerfile'"),
            ("status", "VARCHAR(32) NOT NULL DEFAULT 'queued'"),
            ("progress_step", "VARCHAR(64) DEFAULT NULL"),
            ("progress_pct", "INT NOT NULL DEFAULT 0"),
            ("error_message", "TEXT DEFAULT NULL"),
            ("github_url", "VARCHAR(512) NOT NULL"),
            ("repo_owner", "VARCHAR(64) NOT NULL"),
            ("repo_name", "VARCHAR(128) NOT NULL"),
            ("commit_sha", "CHAR(40) NOT NULL"),
            ("dockerfile_path", "VARCHAR(255) NOT NULL DEFAULT 'Dockerfile'"),
            ("layer_prefix", "VARCHAR(64) NOT NULL"),
            ("profile_name", "VARCHAR(64) NOT NULL"),
            ("ubuntu_base", "VARCHAR(255) NOT NULL"),
            ("base_image_id", "VARCHAR(128) NOT NULL"),
            ("base_image_name", "VARCHAR(255) DEFAULT NULL"),
            ("base_image_checksum", "VARCHAR(128) DEFAULT NULL"),
            ("base_image_os_hash_algo", "VARCHAR(32) DEFAULT NULL"),
            ("base_image_os_hash_value", "VARCHAR(128) DEFAULT NULL"),
            ("base_image_min_disk", "INT DEFAULT NULL"),
            ("planned_layers", "JSON DEFAULT NULL"),
            ("artifact_ids", "JSON DEFAULT NULL"),
            ("build_ids", "JSON DEFAULT NULL"),
            ("completed_at", "DATETIME(6) DEFAULT NULL"),
        ]:
            try:
                await conn.exec_driver_sql(f"ALTER TABLE layer_import_jobs ADD COLUMN {_col} {_def}")
            except Exception:
                pass
        for _idx_sql in [
            "ALTER TABLE layer_import_jobs ADD INDEX ix_layer_import_jobs_status (status)",
            "ALTER TABLE layer_import_jobs ADD INDEX ix_layer_import_jobs_created_at (created_at)",
        ]:
            try:
                await conn.exec_driver_sql(_idx_sql)
            except Exception:
                pass

        # 셀프서비스 프로젝트 관리자 역할 테이블
        try:
            await conn.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS project_roles ("
                "id INT AUTO_INCREMENT PRIMARY KEY,"
                "project_id VARCHAR(64) NOT NULL,"
                "user_id VARCHAR(64) NOT NULL,"
                "role VARCHAR(32) NOT NULL DEFAULT 'manager',"
                "granted_by VARCHAR(64) NOT NULL,"
                "created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),"
                "UNIQUE KEY uq_project_user_role (project_id, user_id, role),"
                "KEY idx_project_roles_project (project_id),"
                "KEY idx_project_roles_user (user_id)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
        except Exception:
            pass

        # 프로젝트 이메일 초대 테이블
        try:
            await conn.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS project_invitations ("
                "id INT AUTO_INCREMENT PRIMARY KEY,"
                "project_id VARCHAR(64) NOT NULL,"
                "invited_email VARCHAR(255) NOT NULL,"
                "invited_user_id VARCHAR(64) DEFAULT NULL,"
                "invited_by VARCHAR(64) NOT NULL,"
                "invited_by_name VARCHAR(255) NOT NULL DEFAULT '',"
                "token_hash VARCHAR(64) NOT NULL UNIQUE,"
                "status VARCHAR(16) NOT NULL DEFAULT 'pending',"
                "keystone_role VARCHAR(64) NOT NULL DEFAULT 'member',"
                "expires_at DATETIME(6) NOT NULL,"
                "accepted_at DATETIME(6) DEFAULT NULL,"
                "created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),"
                "updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),"
                "KEY idx_project_invitations_status (project_id, status),"
                "KEY idx_project_invitations_email (invited_email)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
        except Exception:
            pass

        # Stampede 오토스케일 컬럼 추가 (014_stampede, 없는 경우에만)
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE k3s_clusters ADD COLUMN stampede_enabled TINYINT(1) NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # 이미 존재하면 무시

        for _col_sql in [
            "ALTER TABLE k3s_nodegroups ADD COLUMN stampede_enabled TINYINT(1) NOT NULL DEFAULT 0",
            "ALTER TABLE k3s_nodegroups ADD COLUMN min_size INT NOT NULL DEFAULT 0",
            "ALTER TABLE k3s_nodegroups ADD COLUMN max_size INT NOT NULL DEFAULT 5",
            "ALTER TABLE k3s_nodegroups ADD COLUMN stampede_state JSON DEFAULT NULL",
        ]:
            try:
                await conn.exec_driver_sql(_col_sql)
            except Exception:
                pass  # 이미 존재하면 무시

    _logger.info("데이터베이스 테이블 생성/확인 완료")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends용 세션 제너레이터."""
    if _session_factory is None:
        raise RuntimeError("DB가 초기화되지 않았습니다")
    async with _session_factory() as session:
        yield session


def get_session_factory() -> async_sessionmaker | None:
    return _session_factory


async def close_db() -> None:
    """앱 종료 시 엔진 정리."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        _logger.info("데이터베이스 연결 종료")


def _mask_url(url: str) -> str:
    """비밀번호 마스킹 (로그용)."""
    try:
        from urllib.parse import urlparse, urlunparse

        p = urlparse(url)
        if p.password:
            masked = p._replace(netloc=f"{p.username}:***@{p.hostname}:{p.port}")
            return urlunparse(masked)
    except Exception:
        pass
    return url
