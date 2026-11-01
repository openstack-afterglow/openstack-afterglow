## Why

Flavor automation is currently coupled to a patched, exact-commit Nova fleet and cannot activate on stock Nova. The user requires Afterglow-owned control using standard APIs, explicit administrator host retirement, approved GPU naming/spec templates, and domain-wide project access.

## What Changes

- Persist last-observed compute-host supported inventory; disconnects, maintenance and native directory disappearance never implicitly retire it. Explicit administrator retirement disables a still-present Nova compute service through the standard API and excludes its inventory without deleting VMs or flavors.
- Introduce revisioned administrator GPU automation profiles with exact name slug, display name, primary resource class, per-GPU resource requirements and exact per-GPU flavor extra specs. Builtin catalogs and newly discovered devices do not grant approval.
- Reconcile private standard flavors from retained included hosts and approved profiles; scale GPU request counts and preserve unrelated approved specs.
- Apply each GPU shape's domain resource allowance to all enabled projects of that enabled domain; newly created projects converge on later reconciliation, with no per-project opt-in required.
- **BREAKING** Remove the native-extension capability/qualification gate and replace native-enforcement claims with honest Afterglow-only policy scope, retaining native Nova scheduling/project quota authority and existing immutable flavor ownership.
- Expose host inventory inclusion, GPU profiles and policy scope in administrator UI, all supported locales and bounded responsive surfaces.

## Capabilities

### New Capabilities

- `flavor-automation-policy`: Revisioned host registry and explicit administrator GPU automation approval.

### Modified Capabilities

- `managed-compute-flavors`: Standard-API reconciliation, retained host inventory, approved GPU specifications and per-shape domain project access.
- `domain-compute-pools`: Afterglow policy/admission and stock Placement accounting without native global enforcement claims.

## Impact

Backend automation policy/service/routes, compute pool projections and affected consumers, administrator flavor/domain UI and localization, behavioral tests and operator/architecture documentation. Use existing RuntimeSetting storage, no new SQL schema. Preserve concurrent checkout changes and index; no production rollout, shared DB migration, automatic activation, existing VM changes or paid operations are authorized. Native VM mutation acceptance uses isolated/synthetic native HTTP evidence, clearly separated from live deployment.
