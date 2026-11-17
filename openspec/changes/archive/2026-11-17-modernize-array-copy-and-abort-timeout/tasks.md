# Tasks

- [x] 1.1 Run `legacy-scan`, check every finding against its guide rubric, and list the ones that stay.
- [x] 1.2 Replace spread-and-sort / reverse-find with `toSorted` / `findLast` for declared array receivers (30 frontend files).
- [x] 1.3 `api-lane.mjs`: `AbortSignal.timeout`; `service-verify-http.mjs`: `{ cause }`.
- [x] 1.4 Revert `Promise.withResolvers` and `Map.groupBy` edits that the Node 20 SSR runtime cannot run.
- [x] 2.1 Verify: `svelte-check` 0 errors / 15 warnings (unchanged), frontend vitest 593 files / 8004 tests, `node --test` latency + service-verify 37 tests, hanging-server proof of the `deadline` result (302 ms for a 300 ms timeout).
- [x] 3.1 CHANGELOG.
