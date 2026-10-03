## Why

Volume and database backup routes and actions exist, but browser-local beta preferences can hide them (a previously stored opt-out overrides the current default). File Storage exposes snapshots, not a real backup workflow. The reported sidebar omits all three backup destinations.

## What Changes

- Promote existing volume and database backup routes, inline actions, and restore flows to standard, always-visible features; remove obsolete beta preferences and stale opt-outs.
- File Storage share backup is excluded from this release by the operator: the Manila data node lacks an independent NFS backup repository and mount access for native CephFS shares. Snapshots remain distinct from backups; no unsupported share-backup UI or API is exposed.
- Make the sidebar and command palette agree with the available backup routes. Keep tenant ownership, project switching, failure visibility, and existing non-backup beta gates.
- Validate the changed paths and publish the required images. The operator deferred production Kolla-Ansible deployment until the pending Lumen compatibility release; do not replace private configuration or unrelated services.

## Capabilities

### New Capabilities

- None in this release. Share backup lifecycle remains pending a separately verified Manila storage and restore data plane.

### Modified Capabilities

- Volume and database backup actions are no longer controlled by browser-local beta flags.
- Backup routes become discoverable in both sidebar and command palette.

## Impact

The frontend backup navigation and pages, beta settings, storage documentation, architecture review and image publishing are affected. Existing localStorage opt-outs no longer hide volume/database backups. Manila share snapshots remain a separate point-in-time feature, not a replacement for backups. No database migration, destructive backup operation or production deployment is part of this release.
