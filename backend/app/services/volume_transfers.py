"""Exact transfer readback and caller-scoped Cinder ownership mutations."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from uuid import UUID

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


def create(info: dict, volume_id: str, name: str | None) -> dict:
    with caller_connection(info) as conn:
        volume = conn.block_storage.get_volume(volume_id)
        if volume_owner(volume) != info["project_id"]:
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


def accept(info: dict, transfer_id: str, auth_key: str) -> tuple[dict, str]:
    exact_transfer_id(transfer_id)
    with caller_connection(info) as conn, operator_connection() as operator:
        _, volume, source = pending(operator, transfer_id, operator=True)
        if source == info["project_id"]:
            raise TransferError(409, "소스와 대상 프로젝트가 같습니다")
        volume_id = required_id(volume, "id")
        try:
            result = cinder.accept_volume_transfer(conn, transfer_id, auth_key)
            required_id(result, "id", transfer_id)
            required_id(result, "volume_id", volume_id)
            # A successful POST alone is not proof of destination ownership.
            try:
                transferred = operator.block_storage.get_volume(volume_id)
            except Exception as exc:
                raise provider_error(exc, operator=True) from None
            required_id(transferred, "id", volume_id)
            if volume_owner(transferred) != info["project_id"]:
                raise TransferError(502, "대상 프로젝트의 볼륨 소유권을 확인할 수 없습니다")
            return result, source
        except Exception as exc:
            error = exc if isinstance(exc, TransferError) else provider_error(exc, accepting=True)
            # A lost response or failed readback may still have transferred
            # ownership. Clear both inventories, but never reissue the POST.
            error.affected_projects = (source, info["project_id"])
            raise error from None


def cancel(info: dict, transfer_id: str) -> str:
    exact_transfer_id(transfer_id)
    with caller_connection(info) as conn:
        _, _, source = pending(conn, transfer_id)
        if source != info["project_id"]:
            raise TransferError(404, "현재 프로젝트의 볼륨 이전을 찾을 수 없습니다")
        cinder.delete_volume_transfer(conn, transfer_id)
        return source
