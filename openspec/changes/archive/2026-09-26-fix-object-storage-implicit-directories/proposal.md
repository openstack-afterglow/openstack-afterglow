## Why

Horizon can navigate nested objects in `chat-attachments`, but Afterglow shows an empty root despite nonzero object count. openstacksdk 3.3.0 drops Swift's `delimiter` from the SDK `objects()` query and does not retain `subdir`, so implicit directories (no stored `path/` marker) disappear. Folder move and recursive delete/trash then attempt to mutate a nonexistent marker after processing children.

## What Changes

- Read Swift container JSON listings through the caller's object-store proxy with `format=json`, `delimiter`, `prefix` and complete marker pagination; retain `subdir` virtual folders, exact stored keys, metadata and SLO size enrichment. Fail on malformed/error/stalled pages instead of caching an empty or partial result.
- Move and recursively delete/trash only stored objects found in flat prefix listings. Include successful logical folder operations in bulk results without creating marker objects; preserve explicit empty folder markers, unrelated similar prefixes, and exact-key operations.
- Treat raw Swift writes as successful only on 2xx (SDK raw requests default to `raise_exc=False`): a failed COPY stops file/folder move, rename and trash before deleting the source; marker create/delete and SLO manifest delete report failures. Same-container identical moves are no-ops; moves into their own descendant or onto another source key are rejected (`400`) before any write.
- Cover hierarchy, pagination, encoding, errors, marker collisions, move/copy ordering, trash/delete and the authenticated route boundary with backend regressions; exercise a disposable Swift fixture via the actual API and browser.

## Capabilities

### New Capabilities

- Navigate implicit nested directories and use existing folder actions without materializing marker objects.

### Modified Capabilities

- Swift object listing and recursive folder move, soft delete and permanent delete behavior; unchanged API schemas and authorization.

## Impact

- `backend/app/services/swift.py` and existing object-storage tests; `docs/api/object-storage.md`, `CHANGELOG.md` and architecture review. No production frontend, upload pipeline, credential, DB or deployment change. Preserve unrelated worktree edits and never mutate the user's production bucket.
