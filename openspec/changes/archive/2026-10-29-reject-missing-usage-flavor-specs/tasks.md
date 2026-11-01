## Implementation Tasks

- [x] Reproduce installed SDK collapsing missing native extra_specs to an empty map. Actual installed SDK/loopback HTTP produced empty specs for a200{} body; source flavor.py170 confirms decoder behavior.
- [x] Add strict raw envelope reader and integrate all affected schedule/annotation callers while preserving valid inline empty maps and no-replay flags.
- [x] Prove missing/null/list/non-string/redirect rejection and valid empty/additive acceptance through native HTTP; affected11files306 regressions pass, including14 new native catalog/consumer cases. Six actual loopback SDK cases passed; Ruff check and774file format check pass.
- [x] Update documentation, architecture/proofs and archive; do not deploy or enable the scheduler. API documentation, architecture and testing receipt updated; real7-module host/image SHA256 parity, final API/worker arm64/amd64 runtime passed.
