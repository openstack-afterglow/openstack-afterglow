## Why

The volume list panel shows attached server UUIDs while the standalone detail page resolves the instance name, and the two detail surfaces present different information and actions. Volumes also cannot be renamed from the list despite Cinder supporting rename.

## What Changes

- Add a project-authorized volume rename API and an editable name workflow reachable from the volume list and shared detail surface, including in-use volumes.
- Resolve attached instance names under the current project, with a truthful UUID fallback if the instance is unavailable.
- Render one shared volume detail component for both list panel and standalone detail route, preserving matching name/status/type/attachments/snapshot/actions and delete behavior.
- Verify stale project/volume requests do not replace the active view and errors remain visible.

## Impact

Cinder volume mutation API, volume detail controller and UI, direct volume route, list action menu, tests, admin/storage docs and architecture review. No schema migration or live volume rename as part of verification.
