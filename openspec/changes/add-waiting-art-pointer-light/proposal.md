# Waiting art pointer light

## Why

Auth screens and the landing hero respond to the pointer through `AfterglowOrbit interactive`. The waiting screens (`LoadingState` surface and `VmResourcePreparation`) reuse the same artwork but do not, so the wait feels static next to the hero. Separately, the instance usage schedule showed the extension reason field even when no extension was chosen, while the backend requires it only for an extended expiry or an existing reason.

## What Changes

- Pass `interactive` from `LoadingState` (surface variant) and `VmResourcePreparation` to `AfterglowOrbit`. Touch input stays ignored, as in the hero.
- Keep the auth shell's `interactive`, already in source, and cover its caller with a wiring test.
- Show the usage schedule reason field only when `extended || value.reason` holds.
- Retry the recent GitHub users load on focus after a failed first load.
- Add wiring tests proving each caller passes `interactive`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. Feature behavior is documented in `DESIGN.md`, `ARCHITECTURE.md`, and `docs/testing.md`; this project has no specs layer.

## Impact

Frontend only: `frontend/src/lib/components/ui/LoadingState.svelte`, `frontend/src/lib/components/wizard/VmResourcePreparation.svelte`, `frontend/src/lib/components/auth/AuthStudioShell.svelte`, `frontend/src/lib/components/instance/UsageScheduleFields.svelte`, `frontend/src/lib/components/wizard/WizardStep5Config.svelte`, their tests, `CHANGELOG.md`, `ARCHITECTURE.md`, `DESIGN.md`, `docs/testing.md`. No backend, API, or deployment change.
