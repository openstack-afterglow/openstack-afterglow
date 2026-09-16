## Context

Volume-backup routes, API clients, ownership checks, and Cinder operations already exist. Their visibility is controlled by the browser-local `betaFeatures` store. `DEFAULT_BETA_FEATURES` is currently not authoritative during initialization: `readFlag` returns `false` for both server rendering and a missing local-storage key. Consequently, changing a declared default alone would not affect a fresh browser.

## Goals / Non-Goals

**Goals:**
- Make the declared feature defaults authoritative on SSR and when a browser has no saved preference.
- Show volume-backup navigation and flows by default.
- Preserve an explicit per-browser choice to turn volume backups off.
- Leave every unrelated beta feature default unchanged.

**Non-Goals:**
- Do not create, restore, or delete production backups during rollout.
- Do not claim UI visibility proves Cinder backup-service readiness.
- Do not add a server-side feature-flag framework or migrate unrelated local-storage keys.
- Do not alter API authorization or ownership behavior.

## Decisions

### Missing preferences fall back to declared defaults

`readFlag` will return `DEFAULT_BETA_FEATURES[key]` during SSR and when the corresponding local-storage key is absent. A present value remains authoritative: only the literal string `true` enables the feature, so an explicit `false` keeps volume backups hidden for that browser.

This removes the second implicit default embedded in `readFlag` and avoids SSR/client disagreement once one default becomes true.

### Volume backups become the only newly enabled default

`DEFAULT_BETA_FEATURES.volumeBackups` changes to `true`. Other validating features remain false. Navigation already consumes this store, so no route-specific bypass or duplicate condition is required.

Alternative considered: remove the beta gate entirely. Rejected because that would discard the existing browser-local opt-out and expand the change beyond activation by default.

### Deployment verification separates UI and infrastructure

The release verifies the built frontend revision on every Afterglow controller, the public site configuration that hides disabled Swift and Zun services, and the OpenStack Cinder backup-service state. No production backup resource is created solely as a smoke test.

## Risks / Trade-offs

- Existing browsers with a saved `false` continue to hide volume backups. This preserves explicit user preference; removing the key or enabling the account toggle adopts the new default.
- A visible UI can still fail if the Cinder backup service is down. Deployment verification therefore checks the service separately and reports any infrastructure gap.
- SSR now follows declared defaults. Focused tests cover fresh-browser initialization and explicit opt-out behavior.

## Migration Plan

1. Ship the frontend default and fallback logic with focused regression coverage.
2. Publish and deploy the new frontend digest without changing backend images.
3. Verify controller image IDs, public service flags, and Cinder backup-service readiness.
4. Roll back by restoring the prior frontend digest; no database or API migration is involved.

## Open Questions

None.
