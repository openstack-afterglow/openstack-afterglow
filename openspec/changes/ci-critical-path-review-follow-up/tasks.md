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

### Review round 2 fixes (commit `fix: address CI review round 1`)

- [x] `pr-dedup`: move the decision from inline shell to `scripts/ci/pr-dedup.js`.
  - The step now runs `node scripts/ci/pr-dedup.js`. If the script cannot run (for example after a failed checkout), a fallback writes `skip=false`.
  - The script always exits 0 and writes `skip` once, last. Only equal, valid merge and head trees give `skip=true`.
  - It also rejects a dependabot author (`PR_AUTHOR`). The `::notice::` links the head commit so the merger can check that commit's dev push run.
  - Unit tests (fake exec) cover:
    - a fork (including a fork branch named `dev`) and an unknown repo;
    - a dependabot head ref and a dependabot author;
    - non-dev refs;
    - malformed SHAs (empty, short, upper-case, trailing newline, option prefix);
    - empty or malformed tree hashes;
    - fetch and rev-parse failures, and a non-Error throw;
    - equal and unequal trees.
  - A real-git test runs the CLI in a scratch clone of a `file://` origin with the PR merge commit checked out. It covers equal trees, a fork, dependabot, a malformed SHA, an unfetchable SHA and diverged trees.
- [x] `pr-dedup`: drop the job-level `continue-on-error`, so that an infrastructure failure turns the run red instead of hiding it. The checkout keeps its step-level `continue-on-error`. Rewrite the unverified ARCHITECTURE.md claim about what happens when `pr-dedup` fails.
- [x] Contract hardening. The contract now pins:
  - the `pr-dedup` `run:` block exactly, its env and its permissions, and that it has no job-level `continue-on-error`;
  - that no `skip=true` appears anywhere in the workflow;
  - that `test-frontend`, its vitest shard step and its verify step have no `if:`, `continue-on-error:` or `|| true`;
  - the full `case "$rc"` arms at both guard call sites, where exactly two `*)` error arms fail the leg;
  - that the manifest and Cloud Shell guard steps have no `continue-on-error`.
- [x] `changes`: remove the unused `pull-requests: read`. Keep `packages: read`, with a comment that it is used only by the dev push registry read. The contract pins the exact permissions block.
- [x] `detect-build-targets.js`:
  - `collectEventChanges` flags unexpected basis failures (fetch or diff failure, invalid before SHA);
  - `collectWarnings` emits `::warning::` for them on dev pushes;
  - a zero SHA and a forced push stay quiet.
- [x] `helm-release.yml` `check-changes`:
  - replace the tip-only `git diff HEAD^1 HEAD` (and `fetch-depth: 2`) with `scripts/ci/helm-publish-decision.js`. It reuses `collectEventChanges`, so `github.event.before..github.sha` is compared, and a zero SHA, forced push, invalid before, fetch or diff failure, or exception publishes;
  - add `contents: read`;
  - add unit tests;
  - the contract bans a tip-only diff in every workflow and in every `scripts/ci/*.js` file.
- [x] `test-frontend`: pin Node 22 with `actions/setup-node@v4` before vitest, the same major as `version-check`. Reproduced locally: five jsdom `localStorage` test files pass on Node 24.14.1 (66 tests). On Node 26.3.1, four of them fail (64 tests) because `localStorage` is undefined.
- [x] `test:orchestration` runs the two new test files. A contract checks that every `scripts/ci/*.test.js` is listed there.
- [x] Docs:
  - AGENTS.md (CLAUDE.md) CI rules: the scope now covers every workflow and `scripts/ci/`; rule 8 covers the shared event basis and its warning; rule 9 adds the merger's green-push-run check and keeps the canonical same-repo and tree-identity condition; rule 11 adds gating contracts and scripts over inline shell;
  - ARCHITECTURE.md `CI와 이미지 발행`;
  - `backend/tests/TESTING.md`.
- [x] Verify. Mutation-check 33 single-edit regressions with a scratch harness that restores from memory, and confirm that the worktree diff is unchanged afterwards. All 33 fail the suite. Also run `test:orchestration`, `test:kolla:contract`, `test:unit:backend`, `test:contract`, both real vitest shards with the verifier, ruff, actionlint, and the architecture stamp with `--staged`.

### Post-merge follow-up (needs real GitHub Actions runs)

- [ ] Measure 20+ real runs after merge: the critical-path median and p90 and the per-job times. Record them against the 143 s baseline (median, p90 155 s) in this change. CI rule 1 requires this before any effect is claimed.
- [ ] Confirm on a real dev push:
  - `test-pr` is skipped, and `changes` runs on `test` only;
  - `changes` reads the revision labels (the first push after merge uses the event basis, because existing images are unlabelled);
  - `manifest` verify parses real `docker buildx imagetools inspect` output;
  - the guard reads the branch tip with `gh api .../git/ref/heads/dev`.
- [ ] Confirm on a real dev→main PR that `pr-dedup` skips `test-pr` and its notice links the head commit, and that a diverged PR runs it.
- [ ] Force `pr-dedup` to fail once on a real PR (for example a temporary `exit 1` in the job's setup outside the fail-safe step). Confirm that `test-pr` is scheduled and the `test.yml` inner jobs actually execute. If they are skipped, the run is red but the PR tests never ran. The gate then needs a different design, for example `test-pr` without `needs`, reading the dedup result inside `test.yml`.
- [ ] Confirm on a real multi-commit `main` push that `helm-release.yml` `check-changes` fetches `github.event.before` and publishes only when `helm/afterglow/` changed in the pushed range.
- [ ] Confirm that the frontend shard jobs report Node 22 (`node --version` in the setup-node step log).
- [ ] Decide whether to close the shared `<base>-<arch>` race. The fix is either a SHA-scoped intermediate reference with retention cleanup, or a build-push `digest` handed to the manifest leg through a per-target artifact. Either one must be verified on the self-hosted runner, including re-run semantics.
- [ ] Archive this change with `openspec archive ci-critical-path-review-follow-up --skip-specs --yes` once the items above are done.
