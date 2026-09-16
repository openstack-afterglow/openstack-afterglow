## Implementation Tasks

- [x] Install the `apple-design` skill and confirm the 122 HIG reference pages resolve locally.
- [x] Map HIG rules onto existing Afterglow primitives and verify every claimed primitive, token, path, and quotation against source.
- [x] Add the Apple-derived interaction rules to the matching existing `DESIGN.md` sections without restating rules the document already carries.
- [x] Add the named non-goal section recording the excluded Apple material and the reason for each exclusion.
- [x] Correct the stale `--motion-duration-fast`/`-base`/`-panel` values documented in `DESIGN.md` to match `layout.css` and `tokens.ts`.
- [x] Preserve every `DESIGN.md` sentence asserted by frontend tests and confirm with the design-system test targets.
- [x] Confirm the architecture guard's exclusion rule covers `DESIGN.md` so no `ARCHITECTURE.md` re-stamp is required, and that `npm run docs:check` passes unchanged.
