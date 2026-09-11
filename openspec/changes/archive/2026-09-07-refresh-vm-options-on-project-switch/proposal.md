## Why

The VM creation store loads project-scoped options only when the panel opens. If the active project or the administrator-selected target project changes while the panel remains mounted, the store can retain the first project's flavors and quota snapshot.

## What Changes

- Invalidate project-scoped VM creation options whenever the effective project changes.
- Reload flavor eligibility and quota data under the new project scope.
- Clear selections that belong to the previous project before allowing creation to continue.
- Add regression coverage for switching projects while the VM creation panel remains open.

## Impact

Frontend VM creation state only. Backend eligibility and admission contracts remain authoritative and unchanged.
