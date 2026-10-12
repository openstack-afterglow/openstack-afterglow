## Why

The reported `gitlab boot` backup failed with Cinder HTTP 400: `Backing up an in-use volume must use the force flag.` Afterglow exposes creation for attached volumes but omits `force`. Users must understand and explicitly choose the crash-consistent backup boundary rather than receive an unexplained rejection or have force silently enabled.

## What Changes

- Add optional `force=false` to the existing manual backup request and pass it through the native Cinder SDK.
- Read the owned source volume before creation; reject `in-use` without explicit force with an actionable, safe error. Preserve existing ownership, auth, provider validation and cache/audit behavior; record the force choice in existing activity metadata.
- Both manual creation dialogs show the shared localized in-use warning and an initially unchecked force acknowledgement. Submit requires acknowledgement; selecting another volume or reopening clears it. Normal available-volume creation stays unforced.
- Explain that force permits attached-volume backup, does not detach or overwrite the source, and does not guarantee database/application consistency. Recommend quiescing writes or using service-specific backup procedures when needed.
- Exercise consent/state/ownership boundaries, native SDK wire behavior and actual browser surfaces. Update existing API/user/design/architecture guidance and changelog with evidence.

## Capabilities

### New Capabilities

None: extend the existing volume backup creation contract.

### Modified Capabilities

- Manual volume backups: explicit force and informed consent for attached source volumes.

## Impact

Afterglow backend Cinder adapter and manual backup endpoint, the volume list/detail and backup-list dialogs, four UI locales, focused regression tests and current documentation. No new dependency, DB/schema/migration, endpoint, role, automatic-backup force policy or production change. A forced backup may add I/O load and remain only crash-consistent; request acceptance is not backup completion or recovery proof. Existing automatic backup callers retain `force=false`; do not grant unattended consent implicitly. Production create/restore/delete and deployment are not authorized by this source change.
