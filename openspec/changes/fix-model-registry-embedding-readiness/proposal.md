# Model registry embedding and media readiness

## Why
The deployed model registry omits embedding discovery controls and reports media readiness with generic or raw gate codes. Local dev already contains embedding kind options; hidden media draft state can still leak into embedding requests.

## Changes
- Keep discovery metadata, existing-row kind edits and input-token-only embedding API contract aligned.
- Discard hidden media pricing in embedding validation and payloads.
- Share localized media readiness reasons between administration, image and audio studios; never call a ready route unverified.
- Inspect production read-only and provide operator runbook separately. Do not deploy, mutate production or invent provider support.

## Acceptance
Focused component/API/fixture tests, nine-locale validation, typecheck, desktop/mobile synthetic browser proof, and production root-cause table in coordinator notes.
