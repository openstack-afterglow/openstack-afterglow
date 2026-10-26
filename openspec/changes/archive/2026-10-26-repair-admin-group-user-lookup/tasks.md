## Diagnosis
- [x] Reproduce domain candidate failure and separate it from successful group member lookup.

## Implementation
- [x] Repair confirmed missing native candidate handling without hiding provider/authority failures or widening candidate scope.
- [x] Search name/email/full UUID and show name/email/full UUID/home domain for members and candidates, preserving UUID-targeted edits.
- [x] Distinguish loading/error/empty and support explicit retry without stale scope or candidate publication.

## Verification
- [x] Run focused backend/component/controller regressions and related identity checks.
- [x] Exercise actual backend HTTP and compiled responsive group UI with duplicate names, search/error/retry and exact UUID selection.
- [x] Update architecture/design/API/testing/changelog, run isolated canonical gate and archive evidence; preserve shared state.
