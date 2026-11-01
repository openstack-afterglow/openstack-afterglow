"""Login-family authority and exact native-token cleanup for Cloud Shell.

Redis is the existing credential store. Receipts outlive tickets and retain failed
revocations until the native credential expires; tokens never enter logs/labels.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from app.config import get_settings
from app.services import keystone, session_store
from app.services.cache import _get_redis
from app.services.identity_roles import _to_completion

INDEX = "afterglow:cloud-shell:credentials"
PREFIX = "afterglow:cloud-shell:credential:"
USER_PREFIX = "afterglow:cloud-shell:user-credentials:"
OWNER_PREFIX = "afterglow:cloud-shell:resource-owner:"
_STORE_RECEIPT = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
redis.call('ZADD', KEYS[2], ARGV[3], ARGV[4])
redis.call('ZADD', KEYS[3], ARGV[5], ARGV[4])
local ttl = redis.call('TTL', KEYS[3])
if ttl < tonumber(ARGV[2]) then redis.call('EXPIRE', KEYS[3], ARGV[2]) end
redis.call('SET', KEYS[4], ARGV[6], 'NX')
return 1
"""
_UPDATE_RECEIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local data = cjson.decode(raw)
local patch = cjson.decode(ARGV[1])
if tonumber(ARGV[2]) >= 0 and data['version'] ~= tonumber(ARGV[2]) then return 0 end
if data['cleanup_requested'] == true and (patch['active'] == true or patch['creation_attempted'] == true or patch['home_creation_attempted'] == true) then return 0 end
for k, v in pairs(patch) do data[k] = v end
data['version'] = data['version'] + 1
local ttl = redis.call('PTTL', KEYS[1])
if ttl <= 0 then return 0 end
redis.call('SET', KEYS[1], cjson.encode(data), 'PX', ttl)
return 1
"""
_FINISH_RECEIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local data = cjson.decode(raw)
if data['version'] ~= tonumber(ARGV[1]) or data['token_revoked'] ~= true or data['cleanup_requested'] ~= true then return 0 end
if data['home_creation_attempted'] == true and data['home_resolved'] ~= true then return 0 end
if data['creation_attempted'] == true and (ARGV[4] == '' or (data['container_id'] ~= '' and data['container_id'] ~= ARGV[4])) then return 0 end
if redis.call('GET', KEYS[4]) == ARGV[3] then redis.call('DEL', KEYS[4]) end
if redis.call('GET', KEYS[5]) == ARGV[3] then redis.call('DEL', KEYS[5]) end
if redis.call('GET', KEYS[6]) == ARGV[3] then redis.call('DEL', KEYS[6]) end
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[2], ARGV[2])
redis.call('ZREM', KEYS[3], ARGV[2])
return 1
"""
_CHECK_ACTIVE = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local data = cjson.decode(raw)
if data['active'] ~= true or data['cleanup_requested'] == true or data['token_revoked'] == true then return 0 end
if redis.call('GET', KEYS[2]) ~= ARGV[1] or redis.call('GET', KEYS[3]) ~= ARGV[1] then return 0 end
if redis.call('GET', KEYS[4]) ~= ARGV[1] then return 0 end
return 1
"""


class ShellAuthorityError(RuntimeError):
    """Safe, fail-closed authority error without provider payloads."""


def _project(session: dict) -> str:
    target = session.get("target_project_id")
    return target if isinstance(target, str) else str(session.get("project_id") or "")


def _check_session(session: dict | None, binding: dict) -> dict:
    now = time.time()
    if not isinstance(session, dict) or session.get("blacklisted") is not False:
        raise ShellAuthorityError("Cloud Shell login is no longer active")
    fields = ("user_id", "domain_id", "identity_domain_id", "family_id")
    if any(not binding.get(key) or session.get(key) != binding[key] for key in fields):
        raise ShellAuthorityError("Cloud Shell login identity changed")
    revision = session.get("scope_revision", 0)
    if (
        type(revision) is not int
        or revision != binding.get("scope_revision")
        or _project(session) != binding["project_id"]
    ):
        raise ShellAuthorityError("Cloud Shell workspace changed")
    expiry, started = session.get("exp"), session.get("started_at")
    if (
        type(expiry) not in (int, float)
        or type(started) not in (int, float)
        or not now < expiry
        or not now < started + get_settings().session_timeout_seconds
    ):
        raise ShellAuthorityError("Cloud Shell login expired")
    return session


async def bind_login(token_info: dict) -> dict:
    jti = token_info.get("refresh_jti")
    if not isinstance(jti, str) or not jti:
        raise ShellAuthorityError("A current browser login is required")
    session = await session_store.get_session(jti)
    if not isinstance(session, dict):
        raise ShellAuthorityError("Cloud Shell login is no longer active")
    binding = {
        "family_id": session.get("family_id") or jti,
        "scope_revision": session.get("scope_revision", 0),
        **{key: token_info.get(key) for key in ("user_id", "project_id", "domain_id", "identity_domain_id")},
    }
    # Legacy sessions can acquire a family only through the normal login/refresh
    # writer; a Cloud Shell request must not resurrect a missing authority key.
    return await require_login(binding)


async def require_login(binding: dict) -> dict:
    session = await session_store.get_family_session(binding["family_id"], binding["user_id"])
    return _check_session(session, binding)


def binding_for(session: dict, project_id: str) -> dict:
    return {
        **{key: session[key] for key in ("user_id", "domain_id", "identity_domain_id", "family_id")},
        "scope_revision": session.get("scope_revision", 0),
        "project_id": project_id,
    }


def inspect_native_token(token: str, binding: dict) -> dict:
    """GET the exact subject; never mint extra untracked monitor credentials."""
    from app.services import domain_scope, project_service
    from app.services.native_operation import NativeOperation

    with NativeOperation() as operation:
        access = operation.ks.tokens.validate(token, include_catalog=False)
        if (
            access.auth_token != token
            or access.user_id != binding["user_id"]
            or access.project_id != binding["project_id"]
        ):
            raise ShellAuthorityError("Cloud Shell native subject changed")
        if access.user_domain_id != binding["identity_domain_id"]:
            raise ShellAuthorityError("Cloud Shell identity domain changed")
        context = domain_scope.domain_context(binding["user_id"], binding["domain_id"], operation=operation)
        if context["identity_domain_id"] != binding["identity_domain_id"]:
            raise ShellAuthorityError("Cloud Shell identity domain changed")
        domain_scope.assert_project_domain(binding["domain_id"], binding["project_id"], operation=operation)
        rows = project_service._assignment_rows(
            operation.ks, binding["project_id"], effective=True, user_id=binding["user_id"]
        )
        roles = project_service._access(rows, operation.catalog(), binding["user_id"])["roles"]
        if not {"admin", "member"}.intersection(roles):
            raise ShellAuthorityError("Cloud Shell project write authority was revoked")
        user = keystone.get_identity_user(binding["user_id"], operation=operation)
        return {**context, "user_id": binding["user_id"], "email": user["email"]}


async def require_authority(binding: dict, token: str, *, native: bool) -> None:
    session = await require_login(binding)
    if native:
        identity = await _to_completion(asyncio.to_thread(inspect_native_token, token, binding))
        from app.api.identity.auth import _enforce_session_policy

        await _enforce_session_policy(session, identity)
        await require_login(binding)


async def store_receipt(payload: dict, ticket_deadline: int) -> None:
    now = int(time.time())
    record = {
        "version": 0,
        "lease": payload,
        "ticket_deadline": ticket_deadline,
        "active": False,
        "cleanup_requested": False,
        "token_revoked": False,
        "creation_attempted": False,
        "container_id": "",
        "home_creation_attempted": False,
        "home_resolved": False,
    }
    redis = await _get_redis()
    ttl = max(payload["token_expires_at"] - now + 120, 120)
    created = await redis.eval(
        _STORE_RECEIPT,
        4,
        PREFIX + payload["session_id"],
        INDEX,
        USER_PREFIX + payload["user_fingerprint"],
        OWNER_PREFIX + payload["user_fingerprint"],
        json.dumps(record, separators=(",", ":")),
        ttl,
        ticket_deadline,
        payload["session_id"],
        payload["token_expires_at"],
        payload["active_value"],
    )
    if not created:
        raise ShellAuthorityError("Cloud Shell credential receipt collision")


async def receipt(session_id: str) -> dict | None:
    redis = await _get_redis()
    raw = await redis.get(PREFIX + session_id)
    if raw is None:
        return None
    data = json.loads(raw)
    flags = (
        "active",
        "cleanup_requested",
        "token_revoked",
        "creation_attempted",
        "home_creation_attempted",
        "home_resolved",
    )
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("lease"), dict)
        or type(data.get("version")) is not int
        or data["version"] < 0
        or type(data.get("ticket_deadline")) is not int
        or not isinstance(data.get("container_id"), str)
        or any(type(data.get(field)) is not bool for field in flags)
    ):
        raise ValueError("Cloud Shell credential receipt is malformed")
    return data


async def require_active_owner(session_id: str, active_key: str, heartbeat_key: str, active_value: str) -> None:
    redis = await _get_redis()
    record = await receipt(session_id)
    if record is None:
        raise ShellAuthorityError("Cloud Shell active ownership was lost")
    if not await redis.eval(
        _CHECK_ACTIVE,
        4,
        PREFIX + session_id,
        active_key,
        heartbeat_key,
        OWNER_PREFIX + record["lease"]["user_fingerprint"],
        active_value,
    ):
        raise ShellAuthorityError("Cloud Shell active ownership was lost")


async def update_receipt(session_id: str, *, expected_version: int | None = None, **patch: Any) -> bool:
    redis = await _get_redis()
    return bool(
        await redis.eval(
            _UPDATE_RECEIPT,
            1,
            PREFIX + session_id,
            json.dumps(patch, separators=(",", ":")),
            -1 if expected_version is None else expected_version,
        )
    )


async def revoke_credential(session_id: str, *, expected_version: int | None = None) -> bool:
    record = await receipt(session_id)
    if record is None or (expected_version is not None and record["version"] != expected_version):
        return False
    if not await update_receipt(session_id, expected_version=record["version"], cleanup_requested=True):
        return False
    ticket = record.get("ticket")
    if ticket:
        from app.services.ws_ticket import _ticket_key, compare_delete

        redis = await _get_redis()
        await redis.delete(_ticket_key(ticket))
        await compare_delete("afterglow:cloud-shell:reservation:" + record["lease"]["user_fingerprint"], ticket)
    if record["token_revoked"]:
        return True
    lease = record["lease"]
    if lease["token_expires_at"] > time.time():
        try:
            await _to_completion(asyncio.to_thread(keystone.revoke_token, lease["token"]))
        except Exception:
            return False
    return await update_receipt(session_id, token_revoked=True)


async def finish_receipt(session_id: str, *, container_id: str = "") -> bool:
    """Release exact coordination before removing the final cleanup authority."""
    record = await receipt(session_id)
    if record is None or record.get("token_revoked") is not True:
        return False
    lease = record["lease"]
    redis = await _get_redis()
    return bool(
        await redis.eval(
            _FINISH_RECEIPT,
            6,
            PREFIX + session_id,
            INDEX,
            USER_PREFIX + lease["user_fingerprint"],
            "afterglow:cloud-shell:active:" + lease["user_fingerprint"],
            "afterglow:cloud-shell:heartbeat:" + session_id,
            OWNER_PREFIX + lease["user_fingerprint"],
            record["version"],
            session_id,
            lease["active_value"],
            container_id,
        )
    )


async def revoke_login_credentials(user_id: str, family_id: str | None = None) -> None:
    """Revocation writers mark receipts before returning; relay fails closed."""
    try:
        user_fp = hashlib.sha256(("cloud-shell-v1\0" + user_id).encode()).hexdigest()
        redis = await _get_redis()
        ids = await redis.zrange(USER_PREFIX + user_fp, 0, -1)
        failed = False
        for value in ids:
            sid = value.decode() if isinstance(value, bytes) else value
            try:
                record = await receipt(sid)
                if record is None:
                    await redis.zrem(USER_PREFIX + user_fp, sid)
                    continue
                lease = record["lease"]
                if lease["user_id"] != user_id or (family_id is not None and lease["family_id"] != family_id):
                    continue
                if not await revoke_credential(sid):
                    failed = True
                elif await finish_receipt(sid):
                    continue
            except Exception:
                failed = True
            await redis.zadd(INDEX, {sid: 0})
        if failed:
            raise ShellAuthorityError("Cloud Shell credential revocation remains pending")
    except Exception:
        raise ShellAuthorityError("Cloud Shell credential revocation remains pending") from None
