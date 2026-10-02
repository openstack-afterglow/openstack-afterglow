## Why

The user's canonical local source build created its images successfully but `lumen-migrate` exited 1 on `Duplicate column name 'model_kind'`. The local MariaDB ledger records `019-media-model-registry` / `019_media_model_registry.sql` with SHA-256 `51f2d55f7ec84b8273a8b16ae5c92dd0269cc8dac88b8ac4c7b763b127a98d05`; the current manifest lists the byte-identical migration as `020-media-model-registry`. Reapplying its ALTER TABLE is wrong. The actual dashboard Sidebar also omits image/audio destinations already present in the command-palette navigation and existing Studio routes.

## What Changes

- Recognize only the exact historical media migration identity and verified schema; retain its ledger row and add the canonical 020 row without rerunning DDL. Reject mismatched history or schema. Preserve every other checksum rule, data volume and credential.
- Expose the existing `/dashboard/chat/images` and `/dashboard/chat/audio` pages in the actual AI-chat sidebar, under the existing `services.chat` gate and without beta opt-out. Keep the text-chat link from claiming active state on a sibling Studio page.
- Verify the rebuilt local API/worker migration path and actual desktop/mobile Studio navigation. Inspect native image/TTS/STT catalog responses without paid provider calls.

## Scope and Constraints

Afterglow changes stay on `dev`. Target the untouched Lumen migration runner and isolated new regressions needed by the actual `../lumen` build input; preserve ongoing Responses/media-pricing edits, the provider-identity worktree, all databases, migration SQL/checksums and the real Git indices. No commit, push, production deployment, real inference, provider-key changes or OpenStack resource mutations. Shared docs are integrated by the parent.

## Acceptance

The local migration job completes on the existing historical ledger and on re-execution, provider/model/conversation/key counts are preserved, negative history/schema cases remain fail-closed, Lumen API/worker readiness is observed, and image/audio destinations render and are reachable at mobile/tablet/desktop widths. Page visibility and API capability evidence are distinguished from real-provider media execution.
