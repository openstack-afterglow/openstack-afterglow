# MCP domain origin and member permission preview

## Why
- OAuth connections present an issued project as their origin although authorization spans a single working domain and may include multiple projects. Users need to identify the connection's authorization domain independent of the currently selected workspace.
- Personal MCP key creation shows project cloud authority and Drover/Palimpsest/Waygate permissions as unverified despite a member assignment. Trace the actual caller/project/native-policy path; do not substitute a display-only allow state.

## What Changes
- Project-bound credentials, saved allowed projects, immutable issued-role/access ceilings, exact-owner revocation and audit remain authoritative. Domain presentation must come from trusted saved domain provenance, never the active browser domain or a renamed project identifier. Legacy unprovable origins remain explicitly unknown.
- Correct valid-member preview failures at their cause. Reader/read-key ceilings and genuine service deny/unavailability remain distinct and fail closed. No blanket role grants, service-policy bypass or automatic credential upgrade.
- Update API/UI contracts, nine locale catalogs and behavioral regressions using existing table/status primitives. No unrelated table migration work, dependency change, commit, release or deployment.

## Acceptance
- Two connections from different authorization domains remain distinguishable after workspace/domain selection changes; another owner's connections are excluded.
- Validated member authority is recognized, selected read access remains read-only, and wrong-owner/domain/stale-role/denied/unavailable paths do not become success.
- Prove changed source paths through focused tests and compiled UI/API scenarios; distinguish synthetic fixtures from actual native-service/production evidence. Run current canonical project gate, document verification limits and archive this rapid change without a specs layer.

## Operational boundary
Readonly live-browser diagnostics are attempted only through the existing signed-in relay. No live credentials are exported, no IAM/cloud writes or deployment are authorized. The relay extension was unavailable at investigation start; source and isolated runtime proof cannot be reported as production recovery.
