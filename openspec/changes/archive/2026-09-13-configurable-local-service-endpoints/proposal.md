## Why

The user runs only Afterglow and owned sibling services locally against a real remote OpenStack cluster. Their routing must be selectable through environment/config without changing the remote Kolla installation or its catalog. Existing BFF overrides work, but Compose hardcodes dev URLs and erases prod overrides; Waygate SDK registration lacks the same configured endpoint selection.

## What Changes

- Keep existing SERVICE_{WAYGATE,DROVER,LUMEN,PALIMPSEST}_INTERNAL_URL and [services] *_internal_url settings as the only public endpoint controls.
- Preserve caller/service authentication, project scope, HTTPS production validation and no automatic catalog fallback after explicit endpoint failure.
- Apply configured own-service endpoints to shared OpenStack connection configuration so SDK consumers follow the same choice; leave core OpenStack endpoints and identity unchanged.
- Dev defaults remain local Compose DNS. Operator environment/.env overrides take precedence over non-empty private snapshot [services] values, then dev defaults. Explicit empty environment selects catalog. Generated private compose.env preserves resolved choices.
- Base/prod forward optional endpoint environment values only when set; unset leaves TOML/default catalog intact. Remove forced-empty production override policy. Production HTTPS and secret checks remain unchanged.
- Allow the existing LUMEN_MCP_CONTROL_PLANE_URL to replace the dev reverse connection to Afterglow; document externally reachable callback/public URLs separately from internal API routing.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Consistent configurable endpoint routing across BFF, SDK and Compose deployment modes. Default non-dev behavior remains authenticated Keystone catalog discovery.

## Impact

No API routes/schema, cloud catalog, remote Kolla, TLS policy, data isolation or credentials are changed. Scope is local routing, SDK connection setup, Compose configuration and corresponding docs/regressions. Verify actual SDK and BFF destination selection, default/empty catalog behavior, config/env precedence and the active local stack. Nova 503 remains a separate upstream response; do not substitute success or redirect Nova to a sibling service.
