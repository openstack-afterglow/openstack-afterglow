## Structure and Contracts
- [x] Inspect current native Hub, private packages, managed build/profile/consume source and incumbent rendered dashboard; confirm both use destinations and shared/private scope.
- [x] Define read-only native/admin catalog, provenance/ancestry, query paging and immutable environment-consume contracts without fabricated availability.

## Implementation
- [x] Implement native visible bundle/admin layer catalog and private-package server search with authorization regressions.
- [x] Implement Afterglow BFF, side-effect-free managed catalog and caller-scoped published environment consume/tracking.
- [x] Implement inventory-first administrator origin/ancestry inspection and retain studio/history workflows.
- [x] Implement consumer bundle name/tag discovery, version selection, actual local use and compatible cloud creation with independent source states.

## Verification
- [x] Run exact regressions, affected targets and isolated native/BFF real HTTP/SQL smoke with documented identity/cloud boundaries.
- [x] Exercise actual rendered admin and consumer flows, failure/empty/authority states and responsive/theme behavior; run detector and localization checks.
- [ ] Review/update architecture, API/user/testing/changelog documentation, record evidence and archive completed change.

### Integration blocker
The complete Palimpsest target, disposable MariaDB DB target (167), API contracts (182), and scoped lint/format (25 affected files) pass; exact final target counts are in verification.json. The final shared-source gate still fails: 112 backend failures across enrollment/admin authority/volume-transfer tests, unattributed full-frontend failures and global test_admin_volume_transfer.py F811. Isolated dependency bisect retains the Palimpsest exception and identifies the independent require_admin rewrite as the authority-test trigger. Remaining frontend failures and the volume-transfer marker failure are NOT claimed proven unrelated; only Waygate was separately reproduced on the canonical checkout. No shared guard was reverted. Archive remains blocked on shared integration recovery; see verification.json and docs/testing.md.
