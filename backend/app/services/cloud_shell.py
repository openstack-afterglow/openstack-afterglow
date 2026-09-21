"""Dedicated-project Cloud Shell lifecycle and fail-closed Redis coordination."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.config import Settings, get_settings
from app.services import activity, keystone, zun
from app.services.cache import _get_redis
from app.services.ws_ticket import (
    WebSocketTicketError,
    compare_delete,
    consume_reserved_ticket,
    issue_reserved_ticket,
    peek_ticket,
)

logger = logging.getLogger(__name__)

TICKET_KIND = "cloud-shell"
HEARTBEAT_TTL_SECONDS = 90
HEARTBEAT_INTERVAL_SECONDS = 30
CREATION_GRACE_SECONDS = 120
PROVISION_TIMEOUT_SECONDS = 120
WORKSPACE_LOCK_TTL_SECONDS = 240
RECONCILE_LOCK_TTL_SECONDS = 55
BOOTSTRAP_READY_MARKER = b"AFTERGLOW_CLOUD_SHELL_READY_V1\r\n"
BOOTSTRAP_OK_MARKER = b"AFTERGLOW_CLOUD_SHELL_OK_V1\r\n"
BOOTSTRAP_ERROR_MARKER = b"AFTERGLOW_CLOUD_SHELL_ERROR_V1\r\n"
BOOTSTRAP_MAX_BYTES = 16 * 1024

_VOLUME_METADATA = {
    "afterglow_managed_by": "afterglow",
    "afterglow_purpose": "cloud-shell-home",
    "afterglow_schema": "1",
}
_CONTAINER_LABELS = {
    "afterglow.managed_by": "afterglow",
    "afterglow.purpose": "cloud-shell",
    "afterglow.schema": "1",
}


class CloudShellError(RuntimeError):
    """Safe domain failure suitable for an HTTP/WebSocket error mapping."""

    def __init__(self, code: str, detail: str, *, retain_active: bool = False) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.retain_active = retain_active


class CloudShellConflict(CloudShellError):
    pass


class CloudShellUnavailable(CloudShellError):
    pass


class CloudShellUnauthorized(CloudShellError):
    pass


@dataclass(frozen=True)
class CloudShellLease:
    session_id: str
    user_id: str
    username: str
    project_id: str
    project_name: str
    token: str
    token_expires_at: int
    user_fingerprint: str
    workspace_fingerprint: str
    active_value: str

    @property
    def active_key(self) -> str:
        return _active_key(self.user_fingerprint)

    @property
    def heartbeat_key(self) -> str:
        return _heartbeat_key(self.session_id)


@dataclass
class CloudShellRuntime:
    lease: CloudShellLease
    connection: Any
    container_id: str
    volume_id: str
    labels: dict[str, str]
    exec_session: zun.ZunExecSession
    expires_at: int


@dataclass(frozen=True)
class WorkspaceRecord:
    volume_id: str
    status: str
    size_gib: int
    attachments: tuple[dict[str, Any], ...]


StatusCallback = Callable[[str], Awaitable[None]]


def _fingerprint(*parts: str) -> str:
    value = "\0".join(("cloud-shell-v1", *parts)).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def user_fingerprint(user_id: str) -> str:
    return _fingerprint(user_id)


def workspace_fingerprint(user_id: str, project_id: str) -> str:
    return _fingerprint(user_id, project_id)


def _reservation_key(user_fp: str) -> str:
    return f"afterglow:cloud-shell:reservation:{user_fp}"


def _active_key(user_fp: str) -> str:
    return f"afterglow:cloud-shell:active:{user_fp}"


def _heartbeat_key(session_id: str) -> str:
    return f"afterglow:cloud-shell:heartbeat:{session_id}"


def _workspace_lock_key(workspace_fp: str) -> str:
    return f"afterglow:cloud-shell:workspace-lock:{workspace_fp}"


def _home_name(workspace_fp: str) -> str:
    return f"afterglow-cloud-shell-home-{workspace_fp[:16]}"


def _container_name(session_id: str) -> str:
    return f"afterglow-cloud-shell-{session_id[:16]}"


def _decode_redis(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _parse_expiry(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise CloudShellUnauthorized("token_expiry_invalid", "Keystone token expiry is unavailable") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _active_value(session_id: str, workspace_fp: str) -> str:
    return json.dumps(
        {"session_id": session_id, "workspace": workspace_fp},
        separators=(",", ":"),
        sort_keys=True,
    )


def _ticket_payload_to_lease(payload: dict[str, Any]) -> CloudShellLease:
    fields = (
        "session_id",
        "user_id",
        "username",
        "project_id",
        "project_name",
        "token",
        "user_fingerprint",
        "workspace_fingerprint",
        "active_value",
    )
    if any(not isinstance(payload.get(field), str) for field in fields):
        raise CloudShellUnauthorized("ticket_invalid", "Cloud Shell ticket is invalid")
    expires_at = payload.get("token_expires_at")
    if not isinstance(expires_at, int):
        raise CloudShellUnauthorized("ticket_invalid", "Cloud Shell ticket is invalid")
    lease = CloudShellLease(
        session_id=payload["session_id"],
        user_id=payload["user_id"],
        username=payload["username"],
        project_id=payload["project_id"],
        project_name=payload["project_name"],
        token=payload["token"],
        token_expires_at=expires_at,
        user_fingerprint=payload["user_fingerprint"],
        workspace_fingerprint=payload["workspace_fingerprint"],
        active_value=payload["active_value"],
    )
    expected_user = user_fingerprint(lease.user_id)
    expected_workspace = workspace_fingerprint(lease.user_id, lease.project_id)
    expected_active = _active_value(lease.session_id, expected_workspace)
    if not (
        hmac.compare_digest(lease.user_fingerprint, expected_user)
        and hmac.compare_digest(lease.workspace_fingerprint, expected_workspace)
        and hmac.compare_digest(lease.active_value, expected_active)
    ):
        raise CloudShellUnauthorized("ticket_invalid", "Cloud Shell ticket is invalid")
    return lease


async def issue_cloud_shell_ticket(token_info: dict[str, Any]) -> dict[str, Any]:
    """Re-scope the caller token and reserve the user's singleton shell slot."""
    settings = get_settings()
    if not settings.service_cloud_shell_enabled:
        raise CloudShellUnavailable("disabled", "Cloud Shell is disabled")
    user_id = str(token_info.get("user_id") or "")
    project_id = str(token_info.get("project_id") or "")
    token = str(token_info.get("token") or "")
    if not user_id or not project_id or not token:
        raise CloudShellUnauthorized("identity_missing", "Authenticated project identity is required")
    try:
        scoped = await asyncio.to_thread(keystone.validate_token, token, project_id)
    except Exception:
        raise CloudShellUnavailable("keystone_unavailable", "Keystone token validation failed") from None
    if scoped.get("user_id") != user_id or scoped.get("project_id") != project_id:
        raise CloudShellUnauthorized("scope_mismatch", "Keystone project scope does not match the session")
    expires_at = _parse_expiry(str(scoped.get("expires_at") or ""))
    now = int(time.time())
    if expires_at - now < 120:
        raise CloudShellUnauthorized("token_expiring", "Keystone token expires too soon for Cloud Shell")

    session_id = secrets.token_hex(24)
    user_fp = user_fingerprint(user_id)
    workspace_fp = workspace_fingerprint(user_id, project_id)
    active_value = _active_value(session_id, workspace_fp)
    payload = {
        "session_id": session_id,
        "user_id": user_id,
        "username": str(scoped.get("username") or token_info.get("username") or ""),
        "project_id": project_id,
        "project_name": str(scoped.get("project_name") or token_info.get("project_name") or ""),
        "token": str(scoped.get("token") or ""),
        "token_expires_at": expires_at,
        "user_fingerprint": user_fp,
        "workspace_fingerprint": workspace_fp,
        "active_value": active_value,
    }
    try:
        ticket = await issue_reserved_ticket(
            TICKET_KIND,
            payload,
            ttl_seconds=settings.cloud_shell_ticket_ttl_seconds,
            reservation_key=_reservation_key(user_fp),
            active_key=_active_key(user_fp),
        )
    except WebSocketTicketError:
        raise CloudShellUnavailable("redis_unavailable", "Cloud Shell coordination is unavailable") from None
    if ticket is None:
        raise CloudShellConflict("active_session", "A Cloud Shell session is already active or pending")
    return {
        "ticket": ticket,
        "websocket_path": "/api/v1/cloud-shell/ws",
        "expires_at": now + settings.cloud_shell_ticket_ttl_seconds,
    }


async def consume_cloud_shell_ticket(ticket: str) -> CloudShellLease:
    """Atomically promote a short-lived ticket reservation to an active session."""
    try:
        preview = await peek_ticket(ticket, expected_kind=TICKET_KIND)
    except WebSocketTicketError:
        raise CloudShellUnavailable("redis_unavailable", "Cloud Shell coordination is unavailable") from None
    if preview is None:
        raise CloudShellUnauthorized("ticket_invalid", "Cloud Shell ticket is missing or expired")
    lease = _ticket_payload_to_lease(preview)
    settings = get_settings()
    if lease.token_expires_at - int(time.time()) < 60:
        raise CloudShellUnauthorized("token_expiring", "Keystone token expires too soon for Cloud Shell")
    try:
        result = await consume_reserved_ticket(
            ticket,
            expected_kind=TICKET_KIND,
            reservation_key=_reservation_key(lease.user_fingerprint),
            active_key=lease.active_key,
            active_value=lease.active_value,
            active_ttl_seconds=settings.cloud_shell_max_session_seconds + CREATION_GRACE_SECONDS,
        )
    except WebSocketTicketError:
        raise CloudShellUnavailable("redis_unavailable", "Cloud Shell coordination is unavailable") from None
    if result.status == "conflict":
        raise CloudShellConflict("active_session", "A Cloud Shell session is already active")
    if result.status != "ok" or result.payload is None:
        raise CloudShellUnauthorized("ticket_invalid", "Cloud Shell ticket is missing or expired")
    promoted = _ticket_payload_to_lease(result.payload)
    if not hmac.compare_digest(promoted.active_value, lease.active_value):
        await _release_coordination(lease)
        raise CloudShellUnauthorized("ticket_invalid", "Cloud Shell ticket is invalid")
    try:
        redis = await _get_redis()
        await redis.set(lease.heartbeat_key, lease.active_value, ex=HEARTBEAT_TTL_SECONDS)
    except Exception:
        await _release_coordination(lease)
        raise CloudShellUnavailable("redis_unavailable", "Cloud Shell coordination is unavailable") from None
    return lease


async def refresh_heartbeat(lease: CloudShellLease) -> bool:
    """Refresh liveness only while the active key still belongs to this session."""
    try:
        redis = await _get_redis()
        owner = _decode_redis(await redis.get(lease.active_key))
        if owner is None or not hmac.compare_digest(owner, lease.active_value):
            return False
        await redis.set(lease.heartbeat_key, lease.active_value, ex=HEARTBEAT_TTL_SECONDS)
        return True
    except Exception:
        return False


async def _release_coordination(lease: CloudShellLease) -> None:
    try:
        await compare_delete(lease.heartbeat_key, lease.active_value)
        await compare_delete(lease.active_key, lease.active_value)
    except WebSocketTicketError:
        logger.warning("Cloud Shell coordination release failed (session=%s)", lease.session_id)


@asynccontextmanager
async def _redis_lock(key: str, *, ttl_seconds: int, wait_seconds: float = 5.0) -> AsyncIterator[None]:
    owner = secrets.token_hex(24)
    deadline = time.monotonic() + wait_seconds
    try:
        redis = await _get_redis()
        while not await redis.set(key, owner, ex=ttl_seconds, nx=True):
            if time.monotonic() >= deadline:
                raise CloudShellConflict("workspace_busy", "Cloud Shell workspace is busy")
            await asyncio.sleep(0.1)
    except CloudShellError:
        raise
    except Exception:
        raise CloudShellUnavailable("redis_unavailable", "Cloud Shell coordination is unavailable") from None
    try:
        yield
    finally:
        try:
            await compare_delete(key, owner)
        except WebSocketTicketError:
            logger.warning("Cloud Shell distributed lock release failed")


def _resource_dict(resource: Any) -> dict[str, Any]:
    if isinstance(resource, dict):
        return dict(resource)
    to_dict = getattr(resource, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, dict):
            return data
    return {
        key: getattr(resource, key, None)
        for key in ("id", "name", "status", "size", "metadata", "attachments", "created_at")
    }


def _workspace_metadata(workspace_fp: str, settings: Settings) -> dict[str, str]:
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        f"cloud-shell-home-v1\0{workspace_fp}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        **_VOLUME_METADATA,
        "afterglow_workspace": workspace_fp,
        "afterglow_signature": signature,
    }


def _workspace_record(volume: dict[str, Any]) -> WorkspaceRecord:
    volume_id = volume.get("id")
    status = volume.get("status")
    size = volume.get("size")
    attachments = volume.get("attachments") or []
    if (
        not isinstance(volume_id, str)
        or not volume_id
        or not isinstance(status, str)
        or not isinstance(size, int)
        or not isinstance(attachments, list)
        or not all(isinstance(item, dict) for item in attachments)
    ):
        raise CloudShellUnavailable("cinder_invalid", "Cinder returned malformed workspace data")
    return WorkspaceRecord(volume_id, status.lower(), size, tuple(attachments))


def _discover_workspace_sync(conn: Any, workspace_fp: str, settings: Settings) -> WorkspaceRecord | None:
    expected_name = _home_name(workspace_fp)
    expected_metadata = _workspace_metadata(workspace_fp, settings)
    volumes = [_resource_dict(volume) for volume in conn.block_storage.volumes(details=True)]
    exact: list[dict[str, Any]] = []
    name_collisions: list[dict[str, Any]] = []
    for volume in volumes:
        metadata = volume.get("metadata")
        if volume.get("name") == expected_name:
            name_collisions.append(volume)
        if (
            volume.get("name") == expected_name
            and isinstance(metadata, dict)
            and all(str(metadata.get(key, "")) == value for key, value in expected_metadata.items())
        ):
            exact.append(volume)
    if len(exact) > 1:
        raise CloudShellConflict("workspace_duplicate", "Multiple Cloud Shell home volumes match this workspace")
    if name_collisions and not exact:
        raise CloudShellConflict("workspace_collision", "A non-managed volume collides with the Cloud Shell home name")
    if len(name_collisions) != len(exact):
        raise CloudShellConflict("workspace_collision", "A non-managed volume collides with the Cloud Shell home name")
    if not exact:
        return None
    record = _workspace_record(exact[0])
    if record.size_gib < settings.cloud_shell_home_size_gib:
        raise CloudShellConflict("workspace_size", "Cloud Shell home is smaller than the configured size")
    return record


def _create_workspace_sync(conn: Any, workspace_fp: str, settings: Settings) -> WorkspaceRecord:
    kwargs: dict[str, Any] = {
        "name": _home_name(workspace_fp),
        "size": settings.cloud_shell_home_size_gib,
        "metadata": _workspace_metadata(workspace_fp, settings),
    }
    if settings.cloud_shell_volume_type.strip():
        kwargs["volume_type"] = settings.cloud_shell_volume_type.strip()
    volume = conn.block_storage.create_volume(**kwargs)
    volume = conn.block_storage.wait_for_status(volume, status="available", failures=["error"], wait=180)
    record = _workspace_record(_resource_dict(volume))
    if record.status != "available" or record.attachments:
        raise CloudShellConflict("workspace_busy", "Cloud Shell home did not become available")
    return record


async def _ensure_workspace(conn: Any, lease: CloudShellLease, status: StatusCallback) -> WorkspaceRecord:
    settings = get_settings()
    async with _redis_lock(_workspace_lock_key(lease.workspace_fingerprint), ttl_seconds=WORKSPACE_LOCK_TTL_SECONDS):
        await status("workspace")
        try:
            record = await asyncio.to_thread(_discover_workspace_sync, conn, lease.workspace_fingerprint, settings)
            if record is None:
                record = await asyncio.to_thread(_create_workspace_sync, conn, lease.workspace_fingerprint, settings)
        except CloudShellError:
            raise
        except Exception:
            raise CloudShellUnavailable("cinder_unavailable", "Cloud Shell home storage is unavailable") from None
        if record.status != "available" or record.attachments:
            raise CloudShellConflict("workspace_busy", "Cloud Shell home is attached or not available")
        return record


def _signature(settings: Settings, user_fp: str, workspace_fp: str, session_id: str, expires_at: int) -> str:
    message = "\0".join((user_fp, workspace_fp, session_id, str(expires_at))).encode("utf-8")
    return hmac.new(settings.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _container_labels(lease: CloudShellLease, expires_at: int, settings: Settings) -> dict[str, str]:
    return {
        **_CONTAINER_LABELS,
        "afterglow.user": lease.user_fingerprint,
        "afterglow.workspace": lease.workspace_fingerprint,
        "afterglow.session": lease.session_id,
        "afterglow.created_at": str(int(time.time())),
        "afterglow.expires_at": str(expires_at),
        "afterglow.signature": _signature(
            settings,
            lease.user_fingerprint,
            lease.workspace_fingerprint,
            lease.session_id,
            expires_at,
        ),
    }


def _normalize_labels(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        if isinstance(parsed, dict):
            return {str(key): str(item) for key, item in parsed.items()}
    return {}


def _valid_managed_labels(labels: dict[str, str], settings: Settings) -> bool:
    if any(labels.get(key) != value for key, value in _CONTAINER_LABELS.items()):
        return False
    required = ("afterglow.user", "afterglow.workspace", "afterglow.session", "afterglow.expires_at")
    if any(not labels.get(key) for key in required):
        return False
    try:
        expires_at = int(labels["afterglow.expires_at"])
    except ValueError:
        return False
    expected = _signature(
        settings,
        labels["afterglow.user"],
        labels["afterglow.workspace"],
        labels["afterglow.session"],
        expires_at,
    )
    return hmac.compare_digest(labels.get("afterglow.signature", ""), expected)


def _delete_exact_container_sync(
    conn: Any, container_id: str, expected_labels: dict[str, str], settings: Settings
) -> None:
    container = zun.get_container_raw(conn, container_id)
    if container is None:
        return
    labels = _normalize_labels(container.get("labels"))
    if not _valid_managed_labels(labels, settings) or any(
        labels.get(key) != value for key, value in expected_labels.items()
    ):
        raise CloudShellConflict("container_ownership", "Cloud Shell container ownership is uncertain")
    current_status = str(container.get("status") or "").upper()
    if current_status == "RUNNING":
        zun.stop_container_strict(conn, container_id)
        zun.wait_for_container_status(
            conn,
            container_id,
            accepted={"STOPPED", "EXITED", "CREATED"},
            failed={"ERROR", "DEAD"},
            timeout_seconds=30,
        )
    zun.delete_container_strict(conn, container_id)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if zun.get_container_raw(conn, container_id) is None:
            return
        time.sleep(1)
    raise CloudShellUnavailable("container_delete_timeout", "Cloud Shell container deletion is unverified")


def _wait_workspace_available_sync(conn: Any, volume_id: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        volume = conn.block_storage.get_volume(volume_id)
        if volume is None:
            raise CloudShellUnavailable("workspace_missing", "Cloud Shell home disappeared during cleanup")
        record = _workspace_record(_resource_dict(volume))
        if record.status == "available" and not record.attachments:
            return
        if record.status in {"error", "error_deleting"}:
            raise CloudShellConflict("workspace_error", "Cloud Shell home entered an error state")
        time.sleep(1)
    raise CloudShellUnavailable("workspace_detach_timeout", "Cloud Shell home detach is unverified")


async def provision_session(lease: CloudShellLease, status: StatusCallback) -> CloudShellRuntime:
    """Create one ephemeral container and validated bootstrap exec in the service project."""
    settings = get_settings()
    expires_at = min(
        int(time.time()) + settings.cloud_shell_max_session_seconds,
        lease.token_expires_at - 60,
    )
    if expires_at <= int(time.time()):
        raise CloudShellUnauthorized("token_expiring", "Keystone token expires too soon for Cloud Shell")
    try:
        conn = await asyncio.to_thread(keystone.get_cloud_shell_project_connection)
    except Exception:
        raise CloudShellUnavailable("service_scope_unavailable", "Cloud Shell service project is unavailable") from None

    container_id = ""
    labels = _container_labels(lease, expires_at, settings)
    workspace: WorkspaceRecord | None = None
    try:
        workspace = await _ensure_workspace(conn, lease, status)
        await status("container")
        created = await asyncio.to_thread(
            zun.create_cloud_shell_container,
            conn,
            name=_container_name(lease.session_id),
            image=settings.cloud_shell_image,
            cpu=settings.cloud_shell_cpu,
            memory_mib=settings.cloud_shell_memory_mib,
            network_id=settings.cloud_shell_network_id,
            security_group=settings.cloud_shell_security_group,
            volume_id=workspace.volume_id,
            labels=labels,
        )
        container_id = str(created.get("uuid") or "")
        if not container_id:
            raise CloudShellUnavailable("zun_invalid", "Zun omitted the Cloud Shell container ID")
        await asyncio.to_thread(
            zun.wait_for_container_status,
            conn,
            container_id,
            accepted={"RUNNING"},
            failed={"ERROR", "DEAD", "FAILED"},
            timeout_seconds=PROVISION_TIMEOUT_SECONDS,
        )
        await status("terminal")
        exec_session = await asyncio.to_thread(
            zun.create_exec_session,
            conn,
            container_id,
            trusted_websocket_origin=settings.cloud_shell_zun_websocket_origin,
            command=["/usr/local/bin/afterglow-cloud-shell-bootstrap"],
        )
        return CloudShellRuntime(
            lease=lease,
            connection=conn,
            container_id=container_id,
            volume_id=workspace.volume_id,
            labels=labels,
            exec_session=exec_session,
            expires_at=expires_at,
        )
    except CloudShellError:
        failure: CloudShellError | None = None
        if container_id:
            try:
                await asyncio.to_thread(_delete_exact_container_sync, conn, container_id, labels, settings)
            except Exception:
                failure = CloudShellUnavailable(
                    "cleanup_pending",
                    "Cloud Shell provisioning failed and container cleanup is pending",
                    retain_active=True,
                )
        await asyncio.to_thread(conn.close)
        if failure is not None:
            raise failure from None
        raise
    except Exception:
        cleanup_failed = False
        if container_id:
            try:
                await asyncio.to_thread(_delete_exact_container_sync, conn, container_id, labels, settings)
            except Exception:
                cleanup_failed = True
        await asyncio.to_thread(conn.close)
        if cleanup_failed:
            raise CloudShellUnavailable(
                "cleanup_pending",
                "Cloud Shell provisioning failed and container cleanup is pending",
                retain_active=True,
            ) from None
        raise CloudShellUnavailable("provision_failed", "Cloud Shell provisioning failed") from None


async def cleanup_session(runtime: CloudShellRuntime) -> bool:
    """Delete the exact session container, verify home detach, then release Redis ownership."""
    settings = get_settings()
    cleaned = False
    try:
        await asyncio.to_thread(
            _delete_exact_container_sync,
            runtime.connection,
            runtime.container_id,
            runtime.labels,
            settings,
        )
        await asyncio.to_thread(_wait_workspace_available_sync, runtime.connection, runtime.volume_id)
        cleaned = True
    except Exception:
        logger.warning(
            "Cloud Shell resource cleanup remains pending (session=%s)",
            runtime.lease.session_id,
        )
    finally:
        await asyncio.to_thread(runtime.connection.close)
    if cleaned:
        await _release_coordination(runtime.lease)
    return cleaned


async def abandon_lease(lease: CloudShellLease) -> None:
    """Release an active lease only before a managed container needs reconciliation."""
    await _release_coordination(lease)


def bootstrap_payload(lease: CloudShellLease) -> bytes:
    """Return the single bounded bootstrap line; callers must never log it."""
    settings = get_settings()
    cloud = {
        "auth_type": "v3token",
        "auth": {
            "auth_url": settings.cloud_shell_auth_url,
            "project_id": lease.project_id,
        },
        "region_name": settings.os_region_name,
        "interface": settings.cloud_shell_interface,
        "identity_api_version": 3,
    }
    payload = {
        "clouds": {"afterglow": cloud},
        "secure": {"clouds": {"afterglow": {"auth": {"token": lease.token}}}},
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")) + b"\n"
    )
    if len(encoded) > BOOTSTRAP_MAX_BYTES:
        raise CloudShellUnavailable("bootstrap_payload_too_large", "Cloud Shell authorization payload is too large")
    return encoded


async def workspace_status(token_info: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    user_id = str(token_info.get("user_id") or "")
    project_id = str(token_info.get("project_id") or "")
    if not user_id or not project_id:
        raise CloudShellUnauthorized("identity_missing", "Authenticated project identity is required")
    user_fp = user_fingerprint(user_id)
    workspace_fp = workspace_fingerprint(user_id, project_id)
    try:
        redis = await _get_redis()
        active_raw = _decode_redis(await redis.get(_active_key(user_fp)))
    except Exception:
        raise CloudShellUnavailable("redis_unavailable", "Cloud Shell coordination is unavailable") from None
    try:
        conn = await asyncio.to_thread(keystone.get_cloud_shell_project_connection)
        try:
            workspace = await asyncio.to_thread(_discover_workspace_sync, conn, workspace_fp, settings)
        finally:
            await asyncio.to_thread(conn.close)
    except CloudShellError:
        raise
    except Exception:
        raise CloudShellUnavailable("cinder_unavailable", "Cloud Shell home storage is unavailable") from None
    active_here = False
    if active_raw:
        try:
            active_here = json.loads(active_raw).get("workspace") == workspace_fp
        except (AttributeError, TypeError, ValueError):
            raise CloudShellUnavailable("redis_invalid", "Cloud Shell coordination state is invalid") from None
    return {
        "workspace": "absent" if workspace is None else workspace.status,
        "home_size_gib": workspace.size_gib if workspace is not None else settings.cloud_shell_home_size_gib,
        "session_active": bool(active_raw),
        "session_in_project": active_here,
    }


def _delete_workspace_sync(conn: Any, workspace_fp: str, settings: Settings) -> bool:
    workspace = _discover_workspace_sync(conn, workspace_fp, settings)
    if workspace is None:
        return False
    if workspace.status != "available" or workspace.attachments:
        raise CloudShellConflict("workspace_busy", "Cloud Shell home is attached or not available")
    conn.block_storage.delete_volume(workspace.volume_id, ignore_missing=False, force=False)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if conn.block_storage.get_volume(workspace.volume_id) is None:
            return True
        time.sleep(1)
    raise CloudShellUnavailable("workspace_delete_timeout", "Cloud Shell home deletion is unverified")


async def reset_workspace(token_info: dict[str, Any]) -> bool:
    settings = get_settings()
    user_id = str(token_info.get("user_id") or "")
    project_id = str(token_info.get("project_id") or "")
    if not user_id or not project_id:
        raise CloudShellUnauthorized("identity_missing", "Authenticated project identity is required")
    user_fp = user_fingerprint(user_id)
    workspace_fp = workspace_fingerprint(user_id, project_id)
    try:
        redis = await _get_redis()
        if await redis.exists(_active_key(user_fp)) or await redis.exists(_reservation_key(user_fp)):
            raise CloudShellConflict("active_session", "Close the active Cloud Shell before resetting its home")
    except CloudShellError:
        raise
    except Exception:
        raise CloudShellUnavailable("redis_unavailable", "Cloud Shell coordination is unavailable") from None
    async with _redis_lock(_workspace_lock_key(workspace_fp), ttl_seconds=WORKSPACE_LOCK_TTL_SECONDS):
        try:
            if await redis.exists(_active_key(user_fp)) or await redis.exists(_reservation_key(user_fp)):
                raise CloudShellConflict("active_session", "Close the active Cloud Shell before resetting its home")
            conn = await asyncio.to_thread(keystone.get_cloud_shell_project_connection)
            try:
                return await asyncio.to_thread(_delete_workspace_sync, conn, workspace_fp, settings)
            finally:
                await asyncio.to_thread(conn.close)
        except CloudShellError:
            raise
        except Exception:
            raise CloudShellUnavailable("cinder_unavailable", "Cloud Shell home reset is unavailable") from None


async def record_audit(
    token_info: dict[str, Any],
    *,
    action: str,
    status: activity.ActionStatus,
    error_code: str | None = None,
) -> None:
    await activity.record(
        project_id=str(token_info.get("project_id") or ""),
        user_id=str(token_info.get("user_id") or ""),
        username=str(token_info.get("username") or ""),
        resource_type="cloud_shell",
        action=action,
        status=status,
        error_message=error_code,
    )


def _reconcile_candidates(
    containers: list[dict[str, Any]], settings: Settings
) -> list[tuple[dict[str, Any], dict[str, str]]]:
    by_session: dict[str, list[tuple[dict[str, Any], dict[str, str]]]] = {}
    for container in containers:
        labels = _normalize_labels(container.get("labels"))
        if not _valid_managed_labels(labels, settings):
            continue
        by_session.setdefault(labels["afterglow.session"], []).append((container, labels))
    candidates: list[tuple[dict[str, Any], dict[str, str]]] = []
    for session_id, items in by_session.items():
        if len(items) != 1:
            logger.warning("Cloud Shell reconciliation skipped duplicate session labels (session=%s)", session_id)
            continue
        candidates.append(items[0])
    return candidates


async def reconcile_once() -> dict[str, int]:
    """Delete only proven orphan containers; Redis uncertainty is a no-op."""
    settings = get_settings()
    if not settings.service_cloud_shell_enabled:
        return {"examined": 0, "deleted": 0}
    try:
        async with _redis_lock(
            "afterglow:cloud-shell:reconcile-lock",
            ttl_seconds=RECONCILE_LOCK_TTL_SECONDS,
            wait_seconds=0.05,
        ):
            redis = await _get_redis()
            conn = await asyncio.to_thread(keystone.get_cloud_shell_project_connection)
            try:
                containers = await asyncio.to_thread(zun.list_containers_raw, conn)
                candidates = _reconcile_candidates(containers, settings)
                states: list[tuple[dict[str, Any], dict[str, str], str | None, str | None]] = []
                for container, labels in candidates:
                    heartbeat = _decode_redis(await redis.get(_heartbeat_key(labels["afterglow.session"])))
                    active = _decode_redis(await redis.get(_active_key(labels["afterglow.user"])))
                    states.append((container, labels, heartbeat, active))
            except Exception:
                await asyncio.to_thread(conn.close)
                raise CloudShellUnavailable(
                    "reconcile_unavailable", "Cloud Shell reconciliation state is unavailable"
                ) from None

            deleted = 0
            now = int(time.time())
            for container, labels, heartbeat, _active in states:
                try:
                    created_at = int(labels.get("afterglow.created_at", "0"))
                    expires_at = int(labels["afterglow.expires_at"])
                except ValueError:
                    continue
                expected_active = _active_value(labels["afterglow.session"], labels["afterglow.workspace"])
                heartbeat_valid = bool(heartbeat and hmac.compare_digest(heartbeat, expected_active))
                orphaned = expires_at <= now or (not heartbeat_valid and created_at + CREATION_GRACE_SECONDS <= now)
                if not orphaned:
                    continue
                container_id = container.get("uuid") or container.get("id")
                if not isinstance(container_id, str) or not container_id:
                    continue
                try:
                    await asyncio.to_thread(
                        _delete_exact_container_sync,
                        conn,
                        container_id,
                        labels,
                        settings,
                    )
                except Exception:
                    logger.warning(
                        "Cloud Shell reconciliation could not verify cleanup (session=%s)",
                        labels["afterglow.session"],
                    )
                    continue
                await compare_delete(_heartbeat_key(labels["afterglow.session"]), expected_active)
                await compare_delete(_active_key(labels["afterglow.user"]), expected_active)
                deleted += 1
            await asyncio.to_thread(conn.close)
            return {"examined": len(states), "deleted": deleted}
    except CloudShellConflict:
        return {"examined": 0, "deleted": 0}
    except WebSocketTicketError:
        return {"examined": 0, "deleted": 0}


async def reconciliation_loop() -> None:
    """Run bounded orphan reconciliation until application shutdown cancels the task."""
    settings = get_settings()
    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Cloud Shell reconciliation pass failed", exc_info=True)
        await asyncio.sleep(settings.cloud_shell_reconcile_interval_seconds)
