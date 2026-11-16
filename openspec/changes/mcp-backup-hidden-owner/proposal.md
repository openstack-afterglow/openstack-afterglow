# MCP volume backup tools for member and reader credentials

## Why

After 1.32.23 the owner asked whether the MCP side was fixed too. It was not. The MCP backup adapter (`mcp_control_plane/storage._safe_backup`) requires a visible backup `project_id`, but Cinder's `backup:backup_project_attribute` defaults to `rule:admin_api`, so member and reader credentials never see it. Observed on DMS Lab production (2026-11-16/17, read-only): `afterglow_volume_backup_list` on DMSLAB returned "MCP volume backup data is unavailable", and the same adapter called with the managed member account raised `McpStorageError: Cinder backup ownership cannot be proven` while snapshots (owner attribute visible) listed normally.

## What Changes

1. `storage._backup_owner` fills a hidden (`None`) backup owner with the project the credential was authenticated for, only when `conn._afterglow_authenticated_project_id` equals the requested project. A visible owner always wins; the parent volume still has to be owned by the project.
2. `connection._build_connection` records `access.project_id` as `_afterglow_authenticated_project_id` after it has verified the token is scoped to the grant's target project.
3. Get, list, delete preview and delete request share the path. Delete keeps its write-role gate, `available` status check, parent revalidation and non-force call.

## Capabilities

### Added Capabilities

- `mcp-backup-ownership`
