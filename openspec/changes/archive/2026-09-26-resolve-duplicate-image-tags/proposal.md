## Why

Glance permits multiple image UUIDs with the same Docker-style `repository:tag`. The current catalog repeats the same tag label for each upload and leaves hash identity hidden in the detail panel; the newest upload is not clearly identified as the name/tag's current image. A saving image may not have a calculated hash yet. A name is not an immutable image identity.

## What Changes

- Keep every Glance image and existing UUID-based management/API operations; do not rename or overwrite any image or treat duplicate bytes as one upload.
- Resolve a repository/tag's **current** image from the latest Glance `created_at` timestamp (including fractional precision and offset), with deterministic UUID tie-break; metadata `updated_at`, availability, verification and UI filters never promote an older upload. A still-saving newest image remains current but is not launchable/approvable until active.
- Show each repository tag once in the preview. Show current and older physical versions per tag in user and administrator views with explicit current/previous labels, shortened Glance-calculated hash algorithm/value and UUID distinction. Full SHA-512 stays available in image detail and complete hash/UUID is searchable. If no hash exists, show pending/unavailable and UUID, never invent a digest. Identical-content uploads remain separate by UUID.
- Keep administrator actions, visibility/trust filtering and user launch selection tied to concrete UUIDs. Prevent the VM image picker from presenting two indistinguishable entries for a duplicate name/tag or choosing a stale image by name. Do not silently fall back to an older boot image while the current upload is saving.
- Preserve Glance SDK list/detail responses and verification authority. Existing hash projection is sufficient; carry the already-returned Glance protected flag through the shared `ImageInfo` list enrichment so the existing administrator Delete action remains hidden for protected versions. No new DB, API routes, migration or token semantics.

## Capabilities

### Modified Capabilities

- Repository/tag catalog: one current alias per tag and individually accessible upload versions by SHA-512 plus UUID.
- VM image selection: current active tag target only, with saving current indicated as unavailable rather than silently launching an older same-name image.

## Impact

Frontend catalog grouping, user/admin tag displays, search, VM picker, shared ImageInfo protected metadata, tests and API/design/architecture docs. Frontend, backend and worker image targets are affected by runtime changes. Preserve unrelated pending work and volumes. Validate mobile/tablet/desktop, exact selectors, full gate, linux/arm64 and linux/amd64 builds of affected targets, canonical local deployment and real authenticated duplicate-image browsing. The screenshot's saving image has no digest until Glance completes; this case must retain UUID identity.
