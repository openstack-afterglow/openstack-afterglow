## Why

Consumer instance details currently render backend password-precheck reasons verbatim, including QEMU Guest Agent and image-metadata instructions. The user wants a simple unsupported-instance notice there, while administrator details must retain diagnostic reasons.

## What Changes

- Present an unsupported-instance message for password-precheck `supported=false` on the consumer detail surface, including its button tooltip and an already-open password dialog.
- Keep exact precheck reasons on the administrator detail surface, including an administrator viewing the current project.
- Keep backend precheck results, disabled controls, creator/system-administrator authorization, loading/error handling and password-change requests unchanged.
- Localize the generic notice in the existing Korean, English, Japanese and Simplified Chinese instance namespace.
- Add behavioral regressions for consumer/admin presentation, missing reasons, and supported/loading/error transitions; verify the actual compiled detail surfaces.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- Instance password-support notice: consumer-friendly unsupported state; administrator-only detailed UI diagnostics.

## Impact

Existing instance-detail controller, header/password modal, instance locales and their regression tests. No backend endpoint/response/schema, authorization, configuration, dependency or deployment changes. Preserve concurrent worktree/index changes. Use isolated local builds and synthetic browser/API fixtures; do not mutate real instances, production credentials or shared services.
