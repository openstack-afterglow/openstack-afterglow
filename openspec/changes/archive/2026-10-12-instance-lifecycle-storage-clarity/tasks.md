## Implementation Tasks

- [x] Scope current instance/storage behavior and verify provider quota, protocol and volume expansion constraints.
- [x] 1. Unify password-change and adjacent instance action button styling through shared primitives.
- [x] 2. Show archive only for stopped instances and explain stopped quota use and archive/delete resource effects.
- [x] 3. Show delete/resize alongside archive only when stopped across detail/list/bulk entry points.
- [x] 4. Hide keypair/SSH fields for metadata-confirmed Windows image and volume-backed instances.
- [x] 5. Perform file-storage connection as protocol-correct instance access-list grants with manual connection details and scoped revocation.
- [x] 6. Add attached-volume expansion with stopped-instance checks and truthful disk/guest expansion guidance.
- [x] 7. Update Windows first-initialization timing to approximately 20–30 minutes in four locales and affected guides.
- [x] Exercise changed API/SDK and consumer/admin Chromium surfaces, run scoped regressions and required checks, and preserve evidence with explicit verification limits.
- [x] After runtime proof, update affected existing docs/changelog, complete scoped architecture guards and archive the change.
- [x] During Afterglow-only commit integration, reproduce the already-deleted parent-share cleanup failure (three failing-before delete/bulk/detach cases), move share-authority validation behind authoritative exact-rule absence, retain403/503 fail-closed regressions, and exercise actual Manila/Nova HTTP before the final gate.
