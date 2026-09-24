## Implementation Tasks

### Frontend unit runtime (earlier step in this change)

- [x] Set `pool: 'threads'` in `frontend/vitest.config.ts`. CI-equivalent `--maxWorkers=3` measurement: −14.8 %, and 247/247 files passed twice.
- [x] Add `// @vitest-environment node` to 57 DOM-free test files. 62 files were measured passing under node; the full two-project config passed 247/247 (−9.4 %).

### Backend unit hermeticity and parallelism (earlier step in this change)

- [x] Add `pytest-xdist>=3.8` to the backend `dev` extra and refresh `backend/uv.lock`.
- [x] Run `test:unit:backend` with `-n 4 --dist worksteal` (4 vCPU CI, no `-n auto`), and update the pinned contract string in `scripts/test-target.test.js`. Evidence: 0 failures in 38 local runs, about 2.1× faster wall time.
- [x] Add an autouse network guard to `backend/tests/conftest.py`: non-loopback TCP/UDP connects fail in the unit and contract layers, while `tests/integration/` and `db`-marked tests are exempt. Self-tests are in `backend/tests/test_network_guard.py`.
- [x] Mock Keystone `revoke_token` in `test_auth_jwt.py::TestSessionStore::test_revoke_user_sessions`. The test now asserts that only the target user's tokens are revoked.
- [x] Mock `prom_query.query_instant_multi` in the `test_dashboard_new.py` usage-stats tests.
- [x] Make the `test_mcp_core_tools.py` quota test independent of thread completion order.

### `.github/workflows/test.yml`

- [x] Remove `needs: version-check` from `test-backend`, `test-cloud-shell`, `test-contract`, `test-functional`, `test-frontend` and `detect-live`. `version-check` stays as a parallel job.
- [x] Make `test-frontend` a 2-way matrix (`fail-fast: false`, `shard: [1, 2]`) named `Frontend (unit tests N/2)`:
  - call `./node_modules/.bin/vitest run --shard=N/2` directly, with the default, github-actions and json reporters writing to `runner.temp`;
  - verify the report with `scripts/ci/verify-vitest-shard.js`;
  - run `node --test scripts/run-with-file-log.test.mjs` only when `matrix.shard == 1`.
- [x] Set the MariaDB/PostgreSQL/Redis health checks to 2s interval, 5s timeout and 20 retries, matching the `docker-compose.dev.yml` `test` profile. The live Redis service uses the same values.
- [x] Keep the `test-live` needs list valid. The matrix `test-frontend` is fine, and functional tests still always run.

### `.github/workflows/docker-build.yml`

- [x] Add the `pr-dedup` job:
  - PR only, `contents: read`.
  - Inputs arrive through `env:`, never through shell interpolation.
  - `skip=true` only for the same repository, `head_ref == 'dev'` and merge tree == head tree. Any error gives `skip=false`.
  - The job is `continue-on-error`.
  - Push and dispatch use the `test` caller, which has no `needs` and `if: github.event_name != 'pull_request'`.
  - PRs use the `test-pr` caller of the same `test.yml`, with `needs: pr-dedup` and `if: !cancelled() && needs.pr-dedup.outputs.skip != 'true'`.
  - `changes` needs `[test, test-pr]` and runs when either succeeded.
- [x] Add `scripts/ci/detect-build-targets.js` with unit tests, and call it from `changes`:
  - push uses `github.event.before..HEAD` after a depth-1 fetch; zero, forced, fetch-failure and diff-failure cases build everything;
  - dispatch, `main`, tags and PR keep their existing behaviour;
  - PR `HEAD^1..HEAD` is documented as the full PR diff.
- [x] Add the published-revision basis:
  - Label every image build with `org.opencontainers.image.revision=${{ github.sha }}`.
  - `changes` reads each target's published `:dev` revision. It logs in to the registry, gets `packages: read` and receives `GH_TOKEN` only on push.
  - `ahead`/`identical` adds `git diff <rev> HEAD`. Unreadable and `behind` use the event basis. `diverged` and later errors build the target.
- [x] Give `changes`, `build`, `build-cloud-shell` and `manifest` explicit `!cancelled()` plus result checks, because one of `test`/`test-pr` is always skipped. Keep a skipped ancestor off the push caller so the reusable workflow's inner jobs are unaffected. Update the pinned `build` if-assertion on purpose.
- [x] Per-target manifest:
  - `manifest` runs under `!cancelled() && needs.changes.result == 'success'`, with `fail-fast: false`.
  - `image-revision.js verify` checks that the `<base>-amd64` digest carries `github.sha`; otherwise the leg fails.
  - Tags are created only from the verified digest.
- [x] Stale re-run guard: `image-revision.js guard` compares the published branch-tag revision with `github.sha` and skips the retag with a `::notice::` on `behind`. It runs before `:dev`/`:nightly` move in `manifest`, and before the Cloud Shell build/push.
- [x] Add no `cancel-in-progress` to push runs; a workflow comment records why.

### Contracts

- [x] Pin the new invariants in `scripts/github-actions-contract.test.js`:
  - no `needs: version-check`; functional always runs;
  - the frontend matrix calls vitest directly with `--shard`, file-count verification, and the node test on shard 1 only;
  - health timing matches compose;
  - `pr-dedup` conditions and single write;
  - `test`, `changes`, `build`, `build-cloud-shell` and `manifest` conditions; the event basis with no `HEAD^1..HEAD`;
  - revision labels on every build;
  - manifest verify/guard ordering;
  - no `cancel-in-progress` on push.
- [x] Repoint the Cloud Shell path-rule assertion to `scripts/ci/detect-build-targets.js`, and assert that the workflow invokes the script.
- [x] Wire `scripts/ci/*.test.js` into `test:orchestration`, updating the pinned string in `package.json` and `scripts/test-target.test.js` together.
- [x] Mutation-check the contracts. Each of 11 single-line workflow regressions fails the contract suite, including the `changes` either-caller condition and a `needs` on the push caller.

### Docs, rules, verification

- [x] `ARCHITECTURE.md`: Code map row, new `CI와 이미지 발행` subsection, Maintenance note on `version-check`, verification evidence and command row, Change guide CI row.
- [x] `backend/tests/TESTING.md`: CI job list, including the missing `test-cloud-shell` entry, xdist, the network guard, the frontend shards and `pr-dedup`.
- [x] `docs/testing.md`: unit-layer xdist/network-guard note and direct-vitest shard usage.
- [x] `CLAUDE.md` (a symlink to `AGENTS.md`): new `## CI 파이프라인 성능 규정` section with the canonical rules and Afterglow specifics, and an updated unit-layer line.
- [x] Run actionlint on `.github/workflows/*.yml`. No new issue is introduced. The pre-existing SC2086 info findings remain in unchanged steps and in `helm-release.yml`.
- [x] Run `npm run test:orchestration` and the `scripts/ci/*.test.js` node tests.
- [x] Run a real local `vitest run --shard=1/2` and `--shard=2/2` with the JSON reporter. The shards ran 124 and 123 files, disjoint and together 247. The verifier passed both and rejected an unsharded report.
- [x] Run `npm run docs:check` after `python3 scripts/check_architecture.py --stamp --summary "..."`.
- [x] Run the full local gate (`npm run test:gate` in parts) before the commit:
  - `docs:check` passed;
  - `test:orchestration` 66/66 and `test:kolla:contract` 25/25;
  - `test:unit:backend` 2923 passed on 4 xdist workers;
  - `test:unit:frontend` 247 files / 1422 tests plus 9 node tests;
  - `test:contract` 131 passed;
  - `test:functional` 27 passed, 3 deselected, with the disposable `afterglow-test` project torn down;
  - `lint:backend` clean.
  - actionlint on `test.yml` and `docker-build.yml` reports 0 findings in `test.yml` and 14 info-level SC2086 findings in `docker-build.yml`, all in steps unchanged from `origin/dev` (`origin/dev` had 44).
- [ ] After merge, measure 20+ real runs (critical-path median/p90, per-job times) and record them against the 143 s baseline. This needs real GitHub Actions runs, and CI rule 1 requires it before any effect is claimed. Deferred: needs real GitHub Actions runs after merge.
- [ ] After merge, confirm on a real dev push:
  - `changes` reads the revision labels (the first push after merge falls back to the event basis because existing images are unlabelled);
  - `manifest` verify parses real `imagetools inspect` output;
  - `pr-dedup` skips the dev→main PR.

  Deferred: needs a real dev push and a real dev→main PR after merge.
- [x] Archive with `openspec archive ci-critical-path-overhaul --skip-specs --yes` in the same commit as the change. The two post-merge items above stay open and are archived as deferred follow-ups.

The two open post-merge items, and the review fixes made after archiving, are tracked in the open change `openspec/changes/ci-critical-path-review-follow-up/`.
