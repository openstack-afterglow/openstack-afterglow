## Implementation Tasks

- [x] Parse FROM root Glance name/UUID or Ubuntu tag and Palimpsest parent; collect line errors without weakening build-time validation.
- [x] Centralize active supported-Ubuntu Glance listing and deterministic FROM resolution; remove independent Dockerfile image override from APIs and build plans.
- [x] Implement admin-only read-only lint response with resolved image, completion candidates, syntax diagnostics and new/inherited/total layer counts.
- [x] Cover parser, resolution, lineage, estimate and endpoint auth/failure behavior with backend regressions.
- [x] Implement 600 ms debounced accessible editor lint and candidate suggestions; update mock transport and UI interactions.
- [x] Correct Palimpsest docs, ARCHITECTURE.md and CHANGELOG.md to FROM-only contract.
- [x] Run focused/named targets, real smoke and browser QA, full gate; stamp and pass staged architecture guard.
- [x] Archive completed change.
