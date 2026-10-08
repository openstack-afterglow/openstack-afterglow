## Why

Fix the observed Image Studio UI regression where a project lacking `lumen-images_user` sees model/options checking indefinitely even though the permission guard correctly prevents model requests. Keep the existing permission notices authoritative and all leaf/request fences unchanged.

## What Changes

`ImageStudio.svelte` will render its model readiness/loading/error/empty statuses only while image authority is available. Signed-out help remains unchanged; pending/error/confirmed denial continues through the existing `LumenPermissionNotice`. Do not fake `modelsLoaded`, issue denied requests, add messages/styles or change model loading/preview preservation.

## Evidence and acceptance

Before: actual Chromium grant fixture, 41 screenshots and 197 corrected API receipts, recorded denied `lumen-images_user`, no model request, and an indefinite checking-options label (`afterglow/evidence/afterglow-grant-ui.json`).

After: real source or compiled Chromium shows the permission reason, disabled controls, no checking/no-model/ready status and no model request while denied; pending permission checks show permission loading rather than model loading; allowed model loading/readiness remains functional. Check mobile/tablet/desktop and light/dark using only synthetic identity/model fixtures; no paid inference or production changes. Run the existing required gate and frontend check/build, then archive this fix and publish a new immutable patch without moving v1.30.4. Production cutover remains held for separately reviewed requester-project service grades and auth/storage/recovery prerequisites.
