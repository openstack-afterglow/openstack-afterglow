"""Exact transfer readback and caller-scoped Cinder ownership mutations."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from uuid import UUID

from openstack import resource, utils
from openstack.block_storage.v3.transfer import Transfer

from app.services import cinder, domain_display, keystone
from app.services.user_inventory import scoped_connection


class TransferError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.affected_projects: tuple[str, ...] = ()


def exact_transfer_id(value: str) -> str:
    try:
        valid = str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise TransferError(422, "전체 볼륨 이전 UUID를 입력해 주세요")
    return value


def provider_error(exc: Exception, *, operator: bool = False, accepting: bool = False) -> TransferError:
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", status)
    if status == 404:
        return TransferError(404, "볼륨 이전 또는 볼륨을 찾을 수 없습니다")
    if operator:
        return TransferError(503, "볼륨 이전 조회 서비스를 사용할 수 없습니다")
    # Cinder InvalidAuthKey is native HTTP 400, not 403. Classify it without
    # exposing or recording its message (which may contain credential data).
    if accepting and status == 400:
        messages = (getattr(exc, "details", None), getattr(exc, "message", None))
        if any(isinstance(message, str) and "invalid auth key" in message.lower() for message in messages):
            return TransferError(403, "볼륨 이전 인증 키가 올바르지 않습니다")
    if isinstance(exc, PermissionError) or status in (401, 403):
        return TransferError(403, "현재 프로젝트에서 볼륨 이전 권한이 없습니다")
    if status == 413:
        return TransferError(413, "대상 프로젝트의 볼륨 쿼터가 부족합니다")
    if status in (400, 409):
        return TransferError(409, "볼륨 이전 상태 또는 프로젝트 쿼터를 확인해 주세요")
    return TransferError(502, "볼륨 이전 공급자 요청에 실패했습니다")


def field(row, name: str):
    if isinstance(row, resource.Resource):
        # SDK Resource is a dict subclass, but dict.get reads its stale copied
        # snapshot after descriptor updates. Read the live SDK model first.
        try:
            return getattr(row, name)
        except AttributeError:
            try:
                return row[name]  # Native API-name alias, resolved by the SDK.
            except KeyError:
                return None
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)


def required_id(row, name: str, expected: str | None = None) -> str:
    value = field(row, name)
    if not isinstance(value, str) or not value.strip() or (expected is not None and value != expected):
        raise TransferError(502, "공급자 리소스 식별자를 확인할 수 없습니다")
    return value


def provider_uuid(row, name: str) -> str:
    value = required_id(row, name)
    try:
        return exact_transfer_id(value)
    except TransferError:
        raise TransferError(502, "공급자 리소스 UUID를 확인할 수 없습니다") from None


def volume_owner(volume) -> str:
    raw = volume.to_dict(original_names=True, computed=False) if hasattr(volume, "to_dict") else volume
    owners = [field(volume, "project_id"), field(volume, "os-vol-tenant-attr:tenant_id")]
    if isinstance(raw, Mapping):
        owners.extend([raw.get("project_id"), raw.get("os-vol-tenant-attr:tenant_id")])
    present = [owner for owner in owners if owner is not None and owner != ""]
    if not present or any(not isinstance(owner, str) or not owner.strip() for owner in present):
        raise TransferError(502, "볼륨 소유 프로젝트를 확인할 수 없습니다")
    if any(owner != present[0] for owner in present):
        raise TransferError(502, "볼륨 소유 프로젝트 정보가 일치하지 않습니다")
    return present[0]


@contextmanager
def caller_connection(info: dict):
    if not all(isinstance(info.get(key), str) and info[key] for key in ("token", "user_id", "project_id")):
        raise TransferError(403, "현재 프로젝트 인증 범위를 확인할 수 없습니다")
    try:
        conn, _ = scoped_connection(info["token"], info["user_id"], info["project_id"])
    except Exception as exc:
        raise provider_error(exc) from None
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def operator_connection():
    try:
        conn = keystone.get_admin_project_connection()
    except Exception:
        raise TransferError(503, "볼륨 이전 조회 서비스를 사용할 수 없습니다") from None
    try:
        yield conn
    finally:
        conn.close()


def pending(conn, transfer_id: str, *, lookup: bool = False, operator: bool = False):
    try:
        transfer = conn.block_storage.get_transfer(transfer_id)
        required_id(transfer, "id", transfer_id)
        volume_id = provider_uuid(transfer, "volume_id")
        if field(transfer, "accepted") is True:
            raise TransferError(404, "대기 중인 볼륨 이전을 찾을 수 없습니다")
        volume = conn.block_storage.get_volume(volume_id)
        required_id(volume, "id", volume_id)
        owner = volume_owner(volume)
        supplied_source = field(transfer, "source_project_id")
        if supplied_source is not None and supplied_source != owner:
            raise TransferError(502, "볼륨 이전 소유 프로젝트 정보가 일치하지 않습니다")
        attachments = field(volume, "attachments")
        if not isinstance(attachments, (list, tuple)):
            raise TransferError(502, "볼륨 연결 상태를 확인할 수 없습니다")
        if field(volume, "status") != "awaiting-transfer":
            raise TransferError(404 if lookup else 409, "대기 중인 볼륨 이전을 찾을 수 없습니다")
        if attachments:
            raise TransferError(409, "연결된 볼륨은 이전할 수 없습니다")
        return transfer, volume, owner
    except TransferError:
        raise
    except Exception as exc:
        raise provider_error(exc, operator=lookup or operator) from None


def lookup(transfer_id: str) -> dict:
    exact_transfer_id(transfer_id)
    with operator_connection() as conn:
        transfer, volume, owner = pending(conn, transfer_id, lookup=True)
        try:
            project = conn.identity.get_project(owner)
            required_id(project, "id", owner)
            domain_id = required_id(project, "domain_id")
            domain = conn.identity.get_domain(domain_id)
            required_id(domain, "id", domain_id)
            project_name, domain_name = field(project, "name"), domain_display.display_name(domain)
            size = field(volume, "size")
            if (
                not isinstance(project_name, str)
                or not project_name
                or not isinstance(domain_name, str)
                or not domain_name
            ):
                raise TransferError(502, "소스 프로젝트와 도메인을 확인할 수 없습니다")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise TransferError(502, "볼륨 크기를 확인할 수 없습니다")
            name, volume_name = field(transfer, "name"), field(volume, "name")
            volume_type, created_at = field(volume, "volume_type"), field(transfer, "created_at")
            if any(
                value is not None and not isinstance(value, str)
                for value in (name, volume_name, volume_type, created_at)
            ):
                raise TransferError(502, "볼륨 이전 정보를 확인할 수 없습니다")
            return {
                "id": transfer_id,
                "name": name or "",
                "volume_id": volume.id if not isinstance(volume, Mapping) else volume["id"],
                "created_at": created_at,
                "volume_name": volume_name or "",
                "size": size,
                "volume_type": volume_type,
                "status": "awaiting-transfer",
                "source_project": {"id": owner, "name": project_name},
                "source_domain": {"id": domain_id, "name": domain_name},
            }
        except TransferError:
            raise
        except Exception as exc:
            raise provider_error(exc, operator=True) from None


def own_list(info: dict) -> list[dict]:
    with caller_connection(info) as conn:
        rows = cinder.list_volume_transfers(conn)
        result = []
        for row in rows:
            transfer_id = provider_uuid(row, "id")
            transfer, _, owner = pending(conn, transfer_id)
            if owner != info["project_id"]:
                raise TransferError(502, "공급자가 다른 프로젝트의 볼륨 이전을 반환했습니다")
            result.append(
                {
                    "id": transfer_id,
                    "name": field(transfer, "name") or "",
                    "volume_id": required_id(transfer, "volume_id"),
                    "created_at": field(transfer, "created_at"),
                }
            )
        return result


def create_on_connection(conn, volume_id: str, owner: str, name: str | None) -> dict:
    """One native create path for consumer scope and verified admin executor."""
    volume = conn.block_storage.get_volume(volume_id)
    if volume_owner(volume) != owner:
        raise TransferError(404, "현재 프로젝트의 볼륨을 찾을 수 없습니다")
    required_id(volume, "id", volume_id)
    attachments = field(volume, "attachments")
    if not isinstance(attachments, (list, tuple)):
        raise TransferError(502, "볼륨 연결 상태를 확인할 수 없습니다")
    if field(volume, "status") != "available" or attachments:
        raise TransferError(409, "사용 가능하고 연결되지 않은 볼륨만 이전할 수 있습니다")
    result = cinder.create_volume_transfer(conn, volume_id, name)
    provider_uuid(result, "id")
    required_id(result, "volume_id", volume_id)
    required_id(result, "auth_key")
    return result


def create(info: dict, volume_id: str, name: str | None) -> dict:
    with caller_connection(info) as conn:
        return create_on_connection(conn, volume_id, info["project_id"], name)


def accept_on_connection(conn, operator, project_id: str, transfer_id: str, auth_key: str) -> tuple[dict, str]:
    """Key/policy/quota remain native; success requires exact owner readback."""
    exact_transfer_id(transfer_id)
    _, volume, source = pending(operator, transfer_id, operator=True)
    if source == project_id:
        raise TransferError(409, "소스와 대상 프로젝트가 같습니다")
    volume_id = required_id(volume, "id")
    try:
        result = cinder.accept_volume_transfer(conn, transfer_id, auth_key)
        required_id(result, "id", transfer_id)
        required_id(result, "volume_id", volume_id)
        try:
            transferred = operator.block_storage.get_volume(volume_id)
        except Exception as exc:
            raise provider_error(exc, operator=True) from None
        required_id(transferred, "id", volume_id)
        if volume_owner(transferred) != project_id:
            raise TransferError(502, "대상 프로젝트의 볼륨 소유권을 확인할 수 없습니다")
        if field(transferred, "status") != "available" or field(transferred, "attachments") != []:
            raise TransferError(502, "수신한 볼륨의 사용 가능·미연결 상태를 확인할 수 없습니다")
        return result, source
    except Exception as exc:
        error = exc if isinstance(exc, TransferError) else provider_error(exc, accepting=True)
        error.affected_projects = (source, project_id)
        raise error from None


def accept(info: dict, transfer_id: str, auth_key: str) -> tuple[dict, str]:
    exact_transfer_id(transfer_id)
    with caller_connection(info) as conn, operator_connection() as operator:
        return accept_on_connection(conn, operator, info["project_id"], transfer_id, auth_key)


def cancel(info: dict, transfer_id: str) -> str:
    exact_transfer_id(transfer_id)
    with caller_connection(info) as conn:
        _, _, source = pending(conn, transfer_id)
        if source != info["project_id"]:
            raise TransferError(404, "현재 프로젝트의 볼륨 이전을 찾을 수 없습니다")
        cinder.delete_volume_transfer(conn, transfer_id)
        return source


def enabled_identity(row) -> bool:
    # SDK Project/Domain expose is_enabled; raw Keystone JSON uses enabled.
    # Require explicit true and reject conflicting projections, never truthiness.
    values = [field(row, name) for name in ("is_enabled", "enabled")]
    known = [value for value in values if value is not None]
    return bool(known) and all(value is True for value in known)


def admin_destination(operator, info: dict, domain_id: str, project_id: str):
    """Issue an actual human project token; system admin never implies membership."""
    root_token = info.get("session_token")
    if (
        info.get("is_system_admin") is not True
        or not info.get("token")
        or not info.get("user_id")
        or not isinstance(root_token, str)
        or not root_token.strip()
    ):
        raise TransferError(403, "현재 시스템 관리자 인증이 필요합니다")
    try:
        project = operator.identity.get_project(project_id)
        required_id(project, "id", project_id)
        if required_id(project, "domain_id") != domain_id:
            raise TransferError(409, "대상 프로젝트가 선택한 도메인에 속하지 않습니다")
        domain = operator.identity.get_domain(domain_id)
        required_id(domain, "id", domain_id)
        if not enabled_identity(project) or not enabled_identity(domain):
            raise TransferError(409, "활성 도메인의 활성 대상 프로젝트를 선택해 주세요")
    except TransferError:
        raise
    except Exception as exc:
        raise provider_error(exc) from None
    conn = None
    try:
        conn = keystone.get_openstack_connection(root_token, project_id)
        access = conn.session.auth.get_access(conn.session)
        if (
            access.user_id != info["user_id"]
            or access.project_id != project_id
            or getattr(access, "project_domain_id", None) != domain_id
            or not info.get("identity_domain_id")
            or getattr(access, "user_domain_id", None) != info["identity_domain_id"]
        ):
            raise TransferError(403, "발급된 대상 자격 증명의 사용자·프로젝트·도메인 범위가 일치하지 않습니다")
        issued_token = conn.session.get_token()
        if not isinstance(issued_token, str) or not issued_token:
            raise TransferError(403, "대상 프로젝트의 실제 인증 토큰을 확인할 수 없습니다")
        return conn
    except Exception as exc:
        if conn is not None:
            conn.close()
        if isinstance(exc, TransferError):
            raise
        error = provider_error(exc)
        if error.status_code == 403:
            error.detail = "Keystone이 현재 관리자의 대상 프로젝트 인증을 거부했습니다. 시스템 관리자 권한은 프로젝트 역할을 자동 부여하지 않습니다"
        raise error from None


def admin_cancel(operator, transfer_id: str, expected_owner: str):
    exact_transfer_id(transfer_id)
    _, _, source = pending(operator, transfer_id)
    if source != expected_owner:
        raise TransferError(409, "볼륨 이전의 출발 프로젝트가 변경되었습니다")
    cinder.delete_volume_transfer(operator, transfer_id)
    return source


class _AdminTransfer(Transfer):
    # openstacksdk 3.3 Proxy.transfers passes all_projects but Transfer omits
    # its native all_tenants mapping. Never mutate the shared SDK resource.
    _query_mapping = resource.QueryParameters(all_projects="all_tenants")


def admin_pending_for_volume(operator, volume_id: str) -> list[dict]:
    """Recover only issuance IDs for one exact volume, never its one-time key."""
    volume = operator.block_storage.get_volume(volume_id)
    required_id(volume, "id", volume_id)
    owner = volume_owner(volume)
    result = []
    proxy = operator.block_storage
    base_path = "/volume-transfers" if utils.supports_microversion(proxy, "3.55") else "/os-volume-transfer"
    for transfer in proxy._list(_AdminTransfer, base_path=base_path + "/detail", all_projects=True):
        if field(transfer, "volume_id") != volume_id:
            continue
        transfer_id = provider_uuid(transfer, "id")
        row, _, source = pending(operator, transfer_id)
        if source != owner:
            raise TransferError(409, "볼륨 이전의 출발 프로젝트가 변경되었습니다")
        result.append({"id": transfer_id, "volume_id": volume_id, "name": field(row, "name") or ""})
    if len(result) > 1:
        raise TransferError(502, "볼륨 이전 식별자가 모호합니다")
    if not result and field(volume, "status") == "awaiting-transfer":
        # Native all_tenants may silently narrow a non-admin executor's list.
        # A known pending source cannot become a successful empty recovery.
        raise TransferError(502, "대기 중인 볼륨 이전을 공급자 목록에서 확인할 수 없습니다")
    return result


async def assert_unmanaged(volume, owner: str):
    """Do not strand Palimpsest's durable owner/allocation/cleanup receipts.

    Native markers are conservative blockers, not ownership proof. Removing a
    marker must not bypass SQL/CREATE journals, including unknown native IDs.
    """
    metadata = field(volume, "metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TransferError(502, "볼륨 관리 메타데이터를 확인할 수 없습니다")
    if any(
        str(key).startswith(("afterglow_consume", "afterglow_catalog_consume", "afterglow_run_"))
        for key in metadata or {}
    ):
        raise TransferError(409, "Palimpsest 관리 볼륨은 소유권을 이전할 수 없습니다")
    await assert_unmanaged_id(required_id(volume, "id"), owner)


async def assert_unmanaged_id(volume_id: str, owner: str):
    """Keep durable volume receipts authoritative even after native volume deletion."""
    import json

    from sqlalchemy import select

    from app.database import get_session_factory
    from app.models.db import LayerConsume
    from app.services.cache import _get_redis

    required_id({"id": volume_id}, "id")
    factory = get_session_factory()
    if factory is None:
        raise TransferError(503, "Palimpsest 볼륨 소유권 원장을 확인할 수 없습니다")
    try:
        async with factory() as session:
            rows = (
                await session.execute(
                    select(
                        LayerConsume.id,
                        LayerConsume.project_id,
                        LayerConsume.resources,
                        LayerConsume.resource_snapshot,
                        LayerConsume.cleanup_state,
                    )
                )
            ).all()
            for consume_id, project_id, resources, snapshot, cleanup_state in rows:
                if cleanup_state == "complete":
                    continue
                if isinstance(resources, list):
                    for item in resources:
                        if not isinstance(item, dict):
                            raise TransferError(503, "Palimpsest 볼륨 소유권 원장을 확인할 수 없습니다")
                        if item.get("kind") not in {"upper", "layer", "volume"}:
                            continue
                        if item.get("id") == volume_id:
                            raise TransferError(409, "Palimpsest 소유권 원장에 등록된 볼륨은 이전할 수 없습니다")
                        if (
                            project_id == owner
                            and item.get("id") is None
                            and item.get("state") not in {"rejected", "not_sent", "deleted"}
                        ):
                            raise TransferError(409, "출발 프로젝트에 결과 미확정 Palimpsest 볼륨 할당이 있습니다")
                elif resources is not None and not isinstance(resources, dict):
                    raise TransferError(503, "Palimpsest 볼륨 소유권 원장을 확인할 수 없습니다")
                if project_id == owner and (snapshot or {}).get("catalog_revision"):
                    redis = await _get_redis()
                    raw = await redis.get(f"afterglow:builds:journal:consume:{consume_id}")
                    state = json.loads(raw) if raw else {}
                    raw = await redis.get(
                        f"afterglow:builds:journal:consume:{consume_id}:submit:consumer:{consume_id}:upper"
                    )
                    submitted = json.loads(raw) if raw else {}
                    recovered = (
                        (resources or {}).get("catalog_recovered_ids", {}) if isinstance(resources, dict) else {}
                    )
                    recorded = (state.get("observed_ids") or {}).get(f"consumer:{consume_id}:upper") or (
                        submitted.get("result") or {}
                    ).get("id")
                    identity = recovered.get("upper") or recorded
                    if identity == volume_id or (submitted and not identity and submitted.get("state") != "rejected"):
                        raise TransferError(409, "Palimpsest 볼륨 할당 원장이 이전을 허용하지 않습니다")
    except TransferError:
        raise
    except Exception:
        raise TransferError(503, "Palimpsest 볼륨 소유권 원장을 확인할 수 없습니다") from None
