"""User-scoped default Nova keypair hints; never cloud authorization."""

import hashlib
import json

from fastapi import HTTPException

from app.services import cache


def _key(user_id, identity_domain_id):
    if not user_id or not identity_domain_id:
        raise HTTPException(401, "Canonical account identity is required")
    subject = json.dumps([identity_domain_id, user_id], separators=(",", ":")).encode()
    return "afterglow:ssh-key-preference:" + hashlib.sha256(subject).hexdigest()


async def read(user_id, identity_domain_id):
    key = _key(user_id, identity_domain_id)
    try:
        redis = await cache._get_redis()
        raw = await redis.get(key)
        name = json.loads(raw) if raw is not None else None
        if name is not None and (not isinstance(name, str) or not name or len(name) > 255):
            raise ValueError("Invalid keypair preference")
        return {"keypair_name": name}
    except Exception as exc:
        raise HTTPException(503, "ssh_key_preference_unavailable") from exc


async def save(user_id, identity_domain_id, name):
    key = _key(user_id, identity_domain_id)
    try:
        redis = await cache._get_redis()
        if name is None:
            await redis.delete(key)
        else:
            await redis.set(key, json.dumps(name))
    except Exception as exc:
        raise HTTPException(503, "ssh_key_preference_unavailable") from exc
    return {"keypair_name": name}


async def clear_deleted(user_id, identity_domain_id, name):
    """Do not erase a different default selected while native deletion was pending."""
    key = _key(user_id, identity_domain_id)
    try:
        redis = await cache._get_redis()
        await redis.eval(
            "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end; return 0",
            1,
            key,
            json.dumps(name),
        )
    except Exception as exc:
        raise HTTPException(503, "ssh_key_preference_unavailable") from exc
