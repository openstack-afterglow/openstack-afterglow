# RBAC Project Role Enforcement and Permission Differentiation

## Why

In Afterglow and OpenStack, access control operates on a per-project basis with defined roles:
1. OpenStack Keystone standard roles: `admin`, `member`, `reader`.
2. Afterglow local project roles: `manager` (recorded in `project_roles` database table).

While OpenStack core services enforce RBAC at the service level, Afterglow's BFF layer currently has gaps:
1. **Lack of explicit BFF-level `reader` mutation guards**:
   When a user with only the `reader` role sends mutation requests (`POST`, `PUT`, `PATCH`, `DELETE`) to Afterglow endpoints (such as instances, volumes, networks, keypairs), the BFF does not validate write permissions at admission. Instead, requests proceed to the OpenStack SDK, relying on downstream OpenStack service policies which produce inconsistent error codes or leak internal OpenStack error messages, while Afterglow-only mutations (presets, local state) could bypass OpenStack policies.
2. **Missing user-facing role & permission introspection**:
   Clients and API consumers lack a unified query endpoint to inspect their effective roles and capability flags (`can_write`, `is_manager`, `is_admin`, `is_reader`) for the current active project.
3. **Frontend UI unaware of `reader` status**:
   `frontend/src/lib/stores/auth.ts` only exports `$isAdmin` (system admin), without `$isReader` or `$canWrite` derived stores, leading to UI components showing active creation/deletion action buttons to read-only members.

## What Changes

1. **BFF RBAC Dependency Guards (`backend/app/api/deps.py`)**:
   - Introduce `require_project_write`: Fail-closed check requiring either `is_system_admin`, `admin`, or `member` role. Users with only `reader` role (or lacking write roles) are rejected with `403 Forbidden` (`detail="읽기 전용(reader) 권한으로는 리소스를 생성, 수정 또는 삭제할 수 없습니다."`).
   - Introduce `get_project_permissions`: Helper that evaluates the caller's effective roles and returns structured permission flags (`can_read`, `can_write`, `is_manager`, `is_admin`, `is_reader`, `roles`).
2. **Role & Permission Introspection Endpoint (`backend/app/api/identity/projects.py`)**:
   - Add `GET /api/v1/projects/current/permissions` (and `GET /api/v1/projects/{project_id}/permissions`): Returns current project roles, manager status, and capability flags so API callers can query their exact effective permissions per project.
3. **Apply `require_project_write` to Core Mutation Endpoints**:
   - Keypairs (`POST /api/v1/keypairs`, `DELETE /api/v1/keypairs/{name}`)
   - Instances (`POST /api/v1/instances`, `DELETE /api/v1/instances/{id}`, `POST /api/v1/instances/{id}/action`, etc.)
   - Volumes (`POST /api/v1/volumes`, `DELETE /api/v1/volumes/{id}`, `POST /api/v1/volumes/{id}/action`)
   - Networks / Subnets / Routers / Security Groups mutations
4. **Frontend Auth Store & Read-only Awareness**:
   - Add `isReader` and `canWrite` derived stores in `frontend/src/lib/stores/auth.ts`.
5. **Comprehensive Automated Tests**:
   - Unit tests verifying `reader` role cannot execute mutations and receives 403.
   - Unit tests verifying `member` and `admin` roles can execute mutations.
   - Unit tests for the `/permissions` introspection endpoint.

## Capabilities

### New Capabilities
- `rbac-project-role-introspection`: API callers can query their effective roles and permissions for any accessible project or the current active project context.
- `rbac-project-write-enforcement`: BFF admission guard rejecting write/mutation requests from `reader` accounts with a clear, user-friendly 403 Forbidden response before triggering OpenStack backend calls.

### Modified Capabilities
- `compute-keypairs-api`: Protected by `require_project_write`.
- `compute-instances-api`: Protected by `require_project_write`.
- `storage-volumes-api`: Protected by `require_project_write`.

## Impact

- Files:
  - `backend/app/api/deps.py`
  - `backend/app/api/identity/projects.py`
  - `backend/app/api/compute/keypairs.py`
  - `backend/app/api/compute/instances.py`
  - `backend/app/api/storage/volumes.py`
  - `backend/tests/test_rbac_project_roles.py`
  - `frontend/src/lib/stores/auth.ts`
  - `ARCHITECTURE.md`
- Security: Closes the authorization gap at the BFF perimeter, enforcing strict principle of least privilege between `reader`, `member`, and `manager`/`admin` roles.
