## Why

The Linear-inspired redesign is implemented and gate-verified, but follow-up visual review found a topology page height regression that displaced its bottom legend and a light-theme palette that became too desaturated on chat and other dense workspaces. The frontend type-check baseline also reports 88 errors and 200 warnings across 115 files, and production builds report oversized chunks. These visual and diagnostic regressions leave the redesign cleanup incomplete.

## What Changes

- Restore the topology graph, legend, and summary to normal document flow without the redesign's fixed workspace height.
- Recalibrate light-theme surface, line, ink, and selected-state contrast while preserving the approved neutral shell and semantic/domain accent colors.
- Resolve frontend TypeScript and Svelte diagnostics without weakening compiler, accessibility, or visual-debt checks.
- Remove actionable Svelte compiler warnings in changed and shared UI code while preserving runtime behavior.
- Review oversized production chunks and split only stable dependency boundaries where doing so reduces initial payload without changing route behavior.
- Re-run focused tests, frontend check/build, and the full repository gate.

## Capabilities

### Modified Capabilities

- Topology retains its natural-height graph with the legend and summary below it, without fixed-height overlap or displacement.
- Light-theme workspaces keep neutral graphite/gray surfaces but regain sufficient separation, readable ink, and intentional semantic/domain accents.
- Frontend components, tests, and route compositions satisfy the current Svelte/TypeScript checker without known errors.

## Impact

Frontend source, tests, build configuration, shared design tokens, topology and chat presentation, plus changelog and OpenSpec records. No backend API, authentication, authorization, route URL, service configuration, or deployment changes. Existing dirty flavor-visibility and VM project-switch work remains preserved.