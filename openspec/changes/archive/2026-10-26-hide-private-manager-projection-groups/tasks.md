## Diagnosis
- [x] Trace screenshot error to reserved manager reader-projection guard and ordinary administrator inventory leak.

## Implementation
- [x] Add failing endpoint regressions for fresh/warm and legacy cached projection rows while preserving ordinary groups.
- [x] Filter private groups using the existing canonical predicate without weakening mutation guards.

## Verification
- [x] Run focused backend/API and administrator group UI regressions.
- [x] Exercise actual HTTP and compiled administrator group surface; preserve operational IAM and test cleanup.
- [x] Update architecture/testing/changelog, record gate boundaries and archive completed change.

## Verification boundary
Group-specific acceptance is complete: failing-before/passing-after cache regressions, direct protected DELETE403, actual compiled ordinary DELETE204 with private native groups unchanged, access1638backend/349frontend and scoped2file lint/format pass. Full frozen gate backend9711passed/95skipped but frontend6failed/5327passed across Lumen navigation/model tests; not a green integration gate, no commit/push/deploy. Later contract/functional/global lint lanes were not reached. See verification.json and docs/testing.md.
