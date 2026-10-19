"""Atomic, token-owned creation and compensation of boot-volume policies."""

from app.services import auto_backup as backup_service
from app.services import auto_snapshot as snapshot_service
from app.services import cinder

_REGISTER = """
for i = 1, #KEYS, 3 do
  if redis.call('exists', KEYS[i]) == 1 or redis.call('exists', KEYS[i + 2]) == 1 then
    return 0
  end
  local index_type = redis.call('type', KEYS[i + 1]).ok
  if index_type ~= 'none' and index_type ~= 'set' then
    return redis.error_reply('Protection policy index has an invalid type')
  end
end
for i = 1, #KEYS, 3 do
  local n = math.floor((i - 1) / 3) + 1
  redis.call('set', KEYS[i], ARGV[n + 1])
  redis.call('sadd', KEYS[i + 1], ARGV[1])
end
return 1
"""
_ROLLBACK = """
local removed = 0
for i = 1, #KEYS, 3 do
  local raw = redis.call('get', KEYS[i])
  if raw then
    local ok, cfg = pcall(cjson.decode, raw)
    if ok and cfg.registration_id == ARGV[2] then
      redis.call('del', KEYS[i])
      if not redis.call('get', KEYS[i + 2]) then
        redis.call('srem', KEYS[i + 1], ARGV[1])
      end
      removed = removed + 1
    end
  end
end
return removed
"""


def _keys(module, project_id, volume_id):
    return (
        module._key("config", project_id, volume_id),
        module._ALL_KEY,
        module._key("active", project_id, volume_id),
    )


async def register_volume_protection(
    conn,
    project_id: str,
    volume_id: str,
    *,
    auto_snapshot: bool,
    auto_backup: bool,
    registration_id: str,
) -> None:
    """Preflight using existing worker authority, then create all or none.

    Callers must retain registration_id before awaiting and compensate on any
    exception, including Redis response loss. Existing policies/active journals
    are conflicts, never upserted. No Cinder mutation happens here.
    """
    if not registration_id:
        raise ValueError("A protection registration ID is required")
    modules = []
    if auto_snapshot:
        modules.append(snapshot_service)
    if auto_backup:
        modules.append(backup_service)
    if not modules:
        return
    if getattr(conn, "_afterglow_project_id", None) != project_id:
        raise ValueError("Protection registration requires the native project scope")
    volume = await backup_service._sdk(conn.block_storage.get_volume, volume_id)
    if not cinder._extension_owned(volume, project_id):
        raise ValueError("Source volume ownership could not be confirmed")
    if cinder._extension_field(volume, "status") not in ("available", "in-use"):
        raise ValueError("Source volume is not in a safe protection state")
    keys = []
    policies = []
    for module in modules:
        config = module.build_policy(project_id, volume_id, force=True)
        config["registration_id"] = registration_id
        keys.extend(_keys(module, project_id, volume_id))
        policies.append(backup_service._dump(config))
    redis = await backup_service._get_redis()
    if not await redis.eval(_REGISTER, len(keys), *keys, f"{project_id}:{volume_id}", *policies):
        raise ValueError("A selected protection policy or active operation already exists")


async def rollback_volume_protection(project_id: str, volume_id: str, registration_id: str) -> None:
    """Delete only policies still carrying this attempt's token; never delete journals.

    Conditional rollback is safely repeatable after response loss. Redis failures
    propagate so callers cannot mistake failed compensation for completed cleanup.
    """
    if not registration_id:
        raise ValueError("A protection registration ID is required")
    keys = [
        *_keys(snapshot_service, project_id, volume_id),
        *_keys(backup_service, project_id, volume_id),
    ]
    redis = await backup_service._get_redis()
    await redis.eval(_ROLLBACK, len(keys), *keys, f"{project_id}:{volume_id}", registration_id)
