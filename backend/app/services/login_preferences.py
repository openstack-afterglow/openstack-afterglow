"""Opt-in landing hints in the existing Redis session store, never authority."""

import hashlib
import json

from fastapi import HTTPException

from app.services import cache


def _key(user_id, identity_domain_id):
    if not user_id or not identity_domain_id:
        raise HTTPException(401, "Canonical account identity is required")
    subject = json.dumps([identity_domain_id, user_id], separators=(",", ":")).encode()
    return "afterglow:login-preference:" + hashlib.sha256(subject).hexdigest()


async def read(user_id, identity_domain_id):
    try:
        redis = await cache._get_redis()
        raw = await redis.get(_key(user_id, identity_domain_id))
        if raw is None:
            return {"remember_last_workspace": False}
        value = json.loads(raw)
        if not isinstance(value, dict) or type(value.get("remember_last_workspace")) is not bool:
            raise ValueError("Invalid preference")
        if value["remember_last_workspace"] and any(
            not isinstance(value.get(key), str) or not value[key] or len(value[key]) > 255
            for key in ("domain_id", "project_id")
        ):
            raise ValueError("Invalid saved workspace")
        return value
    except Exception as exc:
        raise HTTPException(503, "login_preference_unavailable") from exc


async def save(user_id, identity_domain_id, enabled, *, domain_id="", project_id=""):
    if enabled and (not domain_id or not project_id):
        raise HTTPException(409, "Select an authorized project before enabling workspace reconnect")
    value = {"remember_last_workspace": enabled}
    if enabled:
        value.update(domain_id=domain_id, project_id=project_id)
    try:
        redis = await cache._get_redis()
        await redis.set(_key(user_id, identity_domain_id), json.dumps(value, separators=(",", ":")))
    except Exception as exc:
        raise HTTPException(503, "login_preference_unavailable") from exc
    return value


async def record(user_id, identity_domain_id, domain_id, project_id):
    """A successful continuation may update an enabled hint, never enable it.

    Atomic compare/update prevents an in-flight switch from undoing opt-out.
    Preference failure must not undo an already published authenticated session.
    """
    if not domain_id or not project_id:
        return
    try:
        redis = await cache._get_redis()
        await redis.eval(
            "local raw = redis.call('GET', KEYS[1]); "
            "if not raw then return 0 end; "
            "local ok, value = pcall(cjson.decode, raw); "
            "if not ok or value.remember_last_workspace ~= true then return 0 end; "
            "value.domain_id = ARGV[1]; value.project_id = ARGV[2]; "
            "redis.call('SET', KEYS[1], cjson.encode(value)); return 1",
            1,
            _key(user_id, identity_domain_id),
            domain_id,
            project_id,
        )
    except Exception:
        return  # Display preference only; native session publication already succeeded.
