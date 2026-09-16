## Implementation Tasks

- [x] Prove the defect against the built stylesheet and the running app rather than by reading source.
- [x] Move the action colour tokens into `@theme static` so Tailwind generates their utilities.
- [x] Measure warm as fill and as text in both themes, and split the two uses instead of sharing one key.
- [x] Migrate the 422 warm text occurrences to the contrast-safe token.
- [x] Give `--focus-ring` a light counterpart.
- [x] Verify in the running app that the utilities resolve and real elements render warm.
- [x] Pass the design target, the frontend unit suite, the build and the full commit gate, then re-stamp.
