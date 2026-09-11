## Why

Afterglow's frontend has accumulated inconsistent navy/blue/purple surfaces, spacing, control geometry, table semantics, responsive cutovers, and dialog behavior across user, administrator, chat, authentication, and public routes. A platform-wide neutral graphite/gray system with the existing orange brand accent will reduce visual noise, improve information density and keyboard/touch accessibility, and preserve the existing operational model.

## What Changes

- Recalibrate the existing dark/light semantic tokens, typography, spacing, motion, radii, focus, and z-index contracts without adding a theme provider, font, icon package, or route-specific palette.
- Rebuild the existing shell around shared header/sidebar geometry, one main landmark, a skip link, responsive navigation, and stable route mounting.
- Extend existing UI primitives for accessible buttons, fields, tables, tabs, toolbars, menus, dialogs, focus trapping, background isolation, and responsive slide panels.
- Migrate every active user, administrator, chat, authentication, invitation, OAuth, error, and landing route to its existing view archetype while preserving URLs, APIs, permissions, feature gates, selection, pagination, and loading/error behavior.
- Restyle the VM creation workspace and fence project-scoped requests with AbortSignal lifecycle guards while keeping global image and administrator metadata sharing intact.
- Add focused regressions for transport races, store destruction, modal focus/isolation, tabs, action menus, fields, disabled links, and semantic resource tables.
- Verify the route matrix in both themes at 390×844, 834×1112, and 1440×1000, plus 320, 767/768, and 1023/1024 boundary checks.

## Capabilities

### New Capabilities

- Shared `ResourceToolbar` composition for existing filter/action controls.
- Shared manually activated keyboard-accessible `Tabs` primitive.
- Shared stacked dialog focus and inert-background action.
- Shared runtime shell geometry and explicit layer CSS variables.

### Modified Capabilities

- Existing theme, shell, navigation, controls, tables, forms, dialogs, slide panels, resource screens, monitoring surfaces, VM wizard, chat workspaces, public landing, and entry flows adopt one neutral/orange visual and responsive contract.
- VM option loading cancels obsolete project-scoped transport and fences all late lifecycle writes without changing the API client contract.

## Impact

Frontend-only behavior and presentation changes under `frontend/`, plus `DESIGN.md`, focused frontend tests, and release documentation. No backend API, runtime service, route URL, authentication transition, authorization rule, feature flag, Nova flavor visibility policy, deployment, or production credential changes. Existing dirty flavor-visibility and project-switch work is preserved and integrated rather than reverted.
