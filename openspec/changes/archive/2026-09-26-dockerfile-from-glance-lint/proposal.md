## Why

Palimpsest Dockerfile builds previously accepted only four literal Ubuntu FROM tags and selected a Glance base image in a separate field. The two independent inputs could disagree. Operators need a single, inspectable base-image selection in the Dockerfile and actionable editor feedback before submitting a build.

## What Changes

- `FROM` alone selects the root image: an exact active supported-Ubuntu Glance image name or UUID, or `ubuntu:<18.04|20.04|22.04|24.04>` when exactly one matching image is available. An exact duplicate name deterministically chooses the newest `created_at` (ID tie-break); ambiguous release tags return copyable image references. A Palimpsest parent FROM inherits its sealed artifact's image snapshot. Remove Dockerfile `base_image_id` from inline, plan, GitHub and lint requests and the studio UI.
- Add admin-only `POST /api/v1/palimpsest/builds/dockerfile/lint`: collect line-numbered syntax errors, show FROM resolution and candidates, estimate new/inherited/total layers against the 25-disk limit; never write jobs or consult the build cache. Keep build-time validation authoritative.
- Show a 600 ms debounced, accessible lint panel in the administrator Dockerfile studio. Preserve plan preview and inline/GitHub import modes; cancel stale lint responses.
- Cover root/parent resolution, ambiguous tags, multiple errors, counts, endpoint authentication, mock transport and responsive editor behavior. Update Palimpsest documentation, architecture and changelog, then verify focused and full gates plus a runtime smoke.

## Capabilities

### New Capabilities

- FROM-driven Glance image resolution and read-only Dockerfile editor lint with layer estimates.

### Modified Capabilities

- Dockerfile parsing, inline and GitHub build preparation, administrator studio workflow.

## Impact

Only the administrator Palimpsest Dockerfile build surface changes. No schema, worker, or storage migration; unsupported Dockerfile instructions and missing build context remain rejected. Builder VM image IDs come from validated Glance snapshots or sealed parent artifacts, never from an independent request override.
