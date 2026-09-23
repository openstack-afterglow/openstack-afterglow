## Implementation Tasks

### Review fixes (commit `fix: address CI overhaul review findings`)

- [x] `test-pr`: prepend `github.event_name == 'pull_request' &&` to its `if`, so it never runs on push or dispatch.
- [x] `changes`: tie each caller result to its event instead of `needs.test.result == 'success' || needs.test-pr.result == 'success'`.
- [x] Contracts:
  - pin both exact expressions and reject a bare `||` between caller results;
  - mutation-check 16 single-line workflow regressions, and all 16 fail the suite:
    - the expression reversions, and the push leg without its event;
    - both 3-argument guards, and both guards keyed to the run's ref instead of the tracked branch;
    - `:nightly` or Cloud Shell nightly tracking `dev`, `:dev` tracking the run's ref, and the dropped `TRACKED_REF` env;
    - the dropped `persist-credentials` and the dropped login outcome;
    - a restored `fetch-depth: 2`;
    - `test-live` without `version-check` or without `test-cloud-shell`.
- [x] Stale re-run guard: add the `<tracked-ref>` argument and a branch-tip read. Skip only when the tip is known, the tip differs from `sha` and compare reports `behind`, so a force-push rollback publishes. Both call sites pass the branch the tag tracks (`:dev`→`dev`, `:nightly`→`main`), not the run's ref, so a `workflow_dispatch` from another branch cannot move `:dev` backward.
- [x] `readRevision`: return `present`, `absent` or `error`. The detector builds on `error`. `::warning::` annotations cover error targets and a failed `registry-login` outcome.
- [x] Detector: remove the PR diff computation, drop `fetch-depth: 2`, and set `persist-credentials: false` on the `changes` checkout.
- [x] `test-live`: add `version-check` and `test-cloud-shell` to its `needs`.
- [x] Shard verifier: require the exact Vitest 4 shard size, and pin the absence of `exclude`, `projects` and `workspace` in `vitest.config.ts`.
- [x] Network guard: record the thread name, and block non-loopback UDP `sendto` in both argument forms.
- [x] Document two known limitations in ARCHITECTURE.md: the shared per-arch tag race (also in the workflow comment), and a rollback that races an in-flight run for the rolled-back commit (mitigation: cancel in-flight runs when rolling back).
- [x] Correct ARCHITECTURE.md, AGENTS.md (CLAUDE.md) rules 3, 8 and 9, `backend/tests/TESTING.md` and the workflow comments.
- [x] Verify:
  - actionlint: 14 SC2086 info findings in `docker-build.yml`, as before;
  - `test:orchestration` 75/75 and `test:kolla:contract`;
  - `test:unit:backend` 2927 passed and `test:contract` 131 passed;
  - `test:functional` 27 passed, with `afterglow-test` torn down;
  - ruff check and format;
  - real `vitest run --shard=1/2` and `--shard=2/2`: 124 and 123 files, disjoint, union 247. The tightened verifier passed both and rejected a mismatched index.
- [x] Re-stamp ARCHITECTURE and pass `check_architecture.py --staged` and `docs:check`.

### Post-merge follow-up (needs real GitHub Actions runs)

- [ ] Measure 20+ real runs after merge: the critical-path median and p90 and the per-job times. Record them against the 143 s baseline (median, p90 155 s) in this change. CI rule 1 requires this before any effect is claimed.
- [ ] Confirm on a real dev push:
  - `test-pr` is skipped, and `changes` runs on `test` only;
  - `changes` reads the revision labels (the first push after merge uses the event basis, because existing images are unlabelled);
  - `manifest` verify parses real `docker buildx imagetools inspect` output;
  - the guard reads the branch tip with `gh api .../git/ref/heads/dev`.
- [ ] Confirm on a real dev→main PR that `pr-dedup` skips `test-pr`, and that a diverged PR runs it.
- [ ] Decide whether to close the shared `<base>-<arch>` race. The fix is either a SHA-scoped intermediate reference with retention cleanup, or a build-push `digest` handed to the manifest leg through a per-target artifact. Either one must be verified on the self-hosted runner, including re-run semantics.
- [ ] Archive this change with `openspec archive ci-critical-path-review-follow-up --skip-specs --yes` once the items above are done.
