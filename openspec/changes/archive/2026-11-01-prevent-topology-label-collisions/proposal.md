## Why

User screenshots show network name/CIDR chips displaced into neighbouring network boxes and competing with card names/addresses. The current HUD checks only the previous world-space zone in a layout band and estimates width from that zone. Rendered screen-space text, cross-band overlaps after dragging, resource cards, domain headings and traffic badges are not collision inputs. At small widths this also reduces names to a 56px chip and suppresses CIDRs.

## What Changes

- Keep network HUD anchors tied to their own zones and pack their measured screen-space bounds together with existing traffic badges.
- Treat projected resource cards (including names and IP rows) and domain headings as occupied bounds; recompute after zoom, pan, drag, locale/font/content and viewport changes.
- Preserve network selectors, full accessible names and CIDRs, retaining only the existing low-zoom instance-count summary. Wrap long content rather than hiding all labels or encoding screenshot-specific positions.
- Show a noninteractive semantic-colour leader from displaced network chips to their original zone anchors.
- Add pure geometry and actual-component regressions plus a reusable synthetic topology fixture for parent browser QA.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- Topology canvas HUD placement is measured, collision-aware and independent of world-space band ordering.

## Impact

Frontend topology only. No API, authorization, native resource, schema, cloud, deployment, loading-artwork or connection-routing changes. Existing graph topology, NIC routing, persisted manual-position intent and selection semantics remain authoritative. Build/tests/lint/browser verification are delegated to the parent integration owner; this change stays unarchived until that evidence is recorded.
