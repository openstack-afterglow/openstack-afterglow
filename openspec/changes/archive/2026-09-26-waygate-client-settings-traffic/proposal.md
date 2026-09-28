## Why
Waygate client issuance/editing must retain real DNS, MTU and PersistentKeepalive settings and make real client traffic visible without fabricated activity.

## What changes
- Extend only the Waygate frontend API/types and client forms for DNS, MTU, PersistentKeepalive (including explicit disabled/zero), server-generated PSK status, and the existing-client reimport requirement.
- Keep authenticated Afterglow BFF requests and existing download/QR behavior.
- Show client-perspective RX/TX totals and report-derived rates with bounded real-sample area waves behind readable card metrics, below client controls. Deduplicate timestamps; reject stale/out-of-order samples and reset deltas; isolate server/project histories.
- Reuse semantic tokens, form/action primitives and responsive mobile/tablet/desktop hierarchy; preserve unrelated feature pages and user-edited mock transport.

## Scope and ownership
ClientSettings owns the upstream contract. This change owns Afterglow frontend composition and focused meaningful behavior/boundary tests. Parent owns integration test/lint/build runs, real authenticated browser smoke, final architecture stamping and change archival. No fake-data surface or new transport is introduced.

## Acceptance
Actual form settings reach the authenticated BFF and remain editable, including keepalive zero. Missing/reset/stale traffic never becomes a synthetic rate or spike. Real report waves stay subtle and pointer-inert as the client metrics' background at <768, 768–1023 and ≥1024 widths; reduced motion is honored. Download and QR remain available.
