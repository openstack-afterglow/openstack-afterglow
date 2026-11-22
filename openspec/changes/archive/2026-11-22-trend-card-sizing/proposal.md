# Trend and VM monitoring card sizing; release 1.32.32

## Why
After the telemetry and metric status lines were removed, the dashboard usage-trend cards and the VM monitoring chart cards still reserved the old heights. The dashboard card kept a 120px content slot, a 56px footer slot and a 44px header row; the VM monitoring card kept a 192px chart slot and a 64px stats slot even when no stats row renders.

## What changes
- Dashboard trend cards: content slot 72px (the plot height), footer slot one line, header row 32px; the loading indicator uses compact padding so loading, ready and empty states keep the same height.
- VM monitoring cards: chart slot 120px (the plot height) and no reserved stats slot; the partial-coverage warning and the optional legend/stats rows are unchanged.
- Bump the application, frontend, backend and Helm versions to 1.32.32 and cut the changelog section.

## Measured
Same fixture, 16px root, one-line content: dashboard card 278px → 182px; VM monitoring chart area 256px minimum → 120px.

## Non-goals
No API, auth, data or copy changes. `/dashboard/usage` already matched its 72px plot.
