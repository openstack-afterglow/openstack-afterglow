## Why

The Identity role page is a read-only flat list and silently turns Keystone failures into an empty catalog. Operators need real role CRUD, selectable downward implication, sorting, and an inheritance tree without exposing privileged roles or management APIs to ordinary users.

## What Changes

- Keep the entire role catalog, CRUD, and implication endpoints behind the server's verified system-admin gate. A project-scoped `admin` or Keystone `manager` name alone must not authorize management.
- Read real Keystone roles and direct inference rules. `A → B` means a holder of A also receives B. Return direct children, transitive children, parent IDs, protected-core status, and system-only status for admin rendering.
- Add role name/description creation and editing, safe deletion, and single-edge add/remove APIs; edge changes are explicit operations, not an allegedly atomic multi-request replacement.
- Protect the built-in `admin`, `manager`, `member`, and `reader` identities against rename/deletion. Block self-inheritance, cycles, unknown IDs, and upward implications including indirect elevation. Hide `admin`, `manager`, and pre-existing aliases implying them on ordinary-user role presentation/assignment paths. Keep internal authorization based on unfiltered verified permissions.
- Add searchable sortable list/tree views, clear direct vs transitive implications, lower-role selection with disabled reasons, protected-role labels, and honest load/mutation errors using existing UI primitives.
- Reject deleting assigned or connected roles instead of cascading grants or inference edges. Invalidate affected caches and sessions after role-privilege changes so stale tokens do not retain removed permissions.
- Distinguish Keystone `manager` from Afterglow's independent project-owner/manager database flag. Do not alter project ownership or enable the legacy admin-project policy.

## Capabilities

### New Capabilities

- System-admin role lifecycle and implication management.
- Sortable role catalog and DAG-safe inheritance tree.

### Modified Capabilities

- Public identity role presentation excludes system-only role names without promoting users or changing their server-side authorization.
- Catalog failures remain errors instead of successful empty lists.

## Impact

Identity role API/service and dashboard composition, public identity/project role projections where exposed, focused authorization/graph regression tests, API/design/architecture/changelog documentation. No schema migration, deployment change, automatic cloud-role seeding, real-cloud write, or existing-system-role reassignment is part of implementation verification.
