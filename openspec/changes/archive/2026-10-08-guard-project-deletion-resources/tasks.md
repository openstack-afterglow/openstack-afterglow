## Implementation Tasks

- [x] Add uncached, target-project resource inspection with ownership filtering, complete pagination, explicit missing-service/unknown results and bounded sample metadata.
- [x] Gate existing admin project DELETE on a new inspection, preserving authentication/cache invalidation and never deleting on resources or unknown reads; update affected contract tests.
- [x] Extend the project-list delete modal with initial inspection, progress, counts, recheck, empty-only confirmation and late-response/auth/project fencing; update four locales and consumer-visible component coverage.
- [x] Exercise actual current-source HTTP/resource SDK paths with isolated providers and browser project-list flows; run affected and canonical backend checks, document scope/race limits, validate scoped architecture and archive the change.
