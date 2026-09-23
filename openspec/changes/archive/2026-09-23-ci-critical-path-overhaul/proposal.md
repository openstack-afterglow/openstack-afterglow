> **Superseded in part** by [`openspec/changes/ci-critical-path-review-follow-up`](../../ci-critical-path-review-follow-up/proposal.md) (review rounds 1-4). This archived proposal is kept as history. Where it differs from that change, `ARCHITECTURE.md` `CI와 이미지 발행` and the CLAUDE.md CI rules describe the current design. Examples of superseded text below: a `continue-on-error` dedup job, a `test-pr` condition without the event conjunct, the `HEAD^1..HEAD` PR diff, a `changes` gate that runs when either caller succeeded, and dedup on tree identity alone.

## Why

The `Layered Tests` workflow (`.github/workflows/test.yml`, called from `.github/workflows/docker-build.yml`) is the gate every dev push and every PR to `main` waits on. The repository is public and uses free GitHub-hosted `ubuntu-latest` runners (4 vCPU), so wall-clock time is the metric that matters, not runner minutes.

Measured baseline, from 40 recent runs:

| Segment | Median |
| --- | --- |
| Critical path, run creation to last required test job | 143 s (p90 155 s) |
| Run creation to `version-check` end; every test job waits on it through `needs:` | 14 s |
| `test-frontend`: vitest Test step 116 s plus 12.5 s job overhead | 126 s |
| `test-backend`: single-process pytest (2902 tests) plus ruff | 70 s |
| `test-functional`; ~30 s is container initialisation (pulls ~14 s, health wait ~12.5 s at `--health-interval 10s`) | 56 s |
| `test-cloud-shell` | 42 s |
| `test-contract` | 31 s |

Vitest 4.1.8 runs 247 jsdom files. Its cumulative phase shares are environment 44.5 %, import 25.2 %, transform 7.3 % and tests 23.2 %, so per-file fixed cost dominates.

The image pipeline has correctness gaps as well as speed gaps:

- **Missed builds.** The `changes` job diffs only `HEAD^1..HEAD`. It missed image builds on 5 of 200 multi-commit dev pushes; for example, run 35109565937 did not rebuild backend for an ownership fix.
- **Failed-run carry-over.** If a target's build fails, it is not rebuilt until a later push happens to touch it again.
- **One failure blocks every manifest.** The `manifest` job needs the whole `build` matrix.
- **Stale re-runs.** No guard exists: re-running an old run once moved `:dev` back to an older SHA (2026-08-28).
- **Duplicate test runs.** 46 SHAs were tested twice, once by the dev push and once by PR #78 (dev→main), whose merge tree equals the dev tree.

Hermeticity problem: two backend unit tests made real network calls whenever a local `afterglow.conf` existed:

- `tests/test_auth_jwt.py::TestSessionStore::test_revoke_user_sessions` revoked fake tokens against the real Keystone.
- `tests/test_dashboard_new.py::test_usage_stats_returns_expected_structure` sent an unpatched Prometheus query.

CI was unaffected because it has no config file, but developer machines were not.

## What Changes

- **Gate parallelism.** `version-check` stays as a parallel job. `test-backend`, `test-cloud-shell`, `test-contract`, `test-functional`, `test-frontend` and `detect-live` no longer declare `needs: version-check`, so they start at t=0. Image builds stay gated: `docker-build.yml` `changes` needs the whole reusable `test` workflow.
- **Frontend sharding.**
  - `test-frontend` becomes a 2-way matrix (`fail-fast: false`, `shard: [1, 2]`) that calls `vitest run --shard=N/2` directly with a JSON report.
  - `scripts/ci/verify-vitest-shard.js` fails the leg unless the shard ran more than 0 files, fewer files than the full suite (counted from the vitest include pattern `src/**/*.{test,spec}.{js,ts}`), and had no failed test or file.
  - `node --test scripts/run-with-file-log.test.mjs` runs only in shard 1.
- **Frontend runtime** (already applied in this change):
  - `pool: 'threads'` in `frontend/vitest.config.ts`.
  - `// @vitest-environment node` on 57 DOM-free test files.
- **Backend parallelism and hermeticity** (already applied in this change):
  - `pytest-xdist` is added as a dev dependency, and `test:unit:backend` runs `-n 4 --dist worksteal`, matching the 4 vCPU runner. `-n auto` is not used.
  - An autouse fixture in `backend/tests/conftest.py` blocks non-loopback TCP/UDP connects in the unit and contract layers. `tests/integration/` and `db`-marked functional tests are exempt.
  - The two non-hermetic tests now mock Keystone `revoke_token` and `prom_query.query_instant_multi`.
  - `test_mcp_core_tools.py` no longer depends on thread completion order.
- **Service health checks.** The MariaDB, PostgreSQL and Redis services use `--health-interval 2s`, `--health-timeout 5s` and `--health-retries 20`, the same values as the `docker-compose.dev.yml` `test` profile.
- **PR dedup.** A PR-only `pr-dedup` job sets `skip=true` only when all three hold:
  - the head repository is this repository;
  - `head_ref` is `dev`;
  - the PR merge commit tree equals the head commit tree.

  Any error yields `skip=false`, and the job is `continue-on-error`. Push and dispatch use a `test` caller that has no `needs` and `if: github.event_name != 'pull_request'`. PRs use a separate `test-pr` caller of the same `test.yml`, with `needs: pr-dedup` and `if: !cancelled() && needs.pr-dedup.outputs.skip != 'true'`. So push, dispatch, dependabot, fork and diverged PRs always test.
- **Image target detection.** `scripts/ci/detect-build-targets.js`, which is unit-tested, replaces the tip-only diff:
  - **Push:** compares `github.event.before..HEAD` after a depth-1 fetch of `before`. An all-zero `before`, a forced push, or a failed fetch or diff builds everything.
  - **PR:** `HEAD^1..HEAD` of the merge commit is the full PR diff (informational; PRs never build).
  - **Dispatch, tags and non-dev refs** keep full-build behaviour.
- **Published-revision basis.**
  - Every image build carries `org.opencontainers.image.revision=${{ github.sha }}`.
  - On dev pushes, the published `:dev` revision is read with `docker buildx imagetools inspect` (read-only, push events only). If the compare API reports that revision as an ancestor of HEAD (`ahead`/`identical`), `git diff <rev> HEAD` is added to that target's basis.
  - An unreadable label falls back to the `event.before` basis.
  - `behind` (a stale re-run) also falls back to the `event.before` basis, and the retag guard handles it.
  - `diverged`, and any error after a revision has been read, builds that target.
- **Per-target manifests.**
  - Each manifest leg runs under `!cancelled() && needs.changes.result == 'success'`, with `fail-fast: false`.
  - Before publishing, the leg verifies that this target's per-arch images carry `github.sha`. It then retags from the verified digest.
- **Stale re-run guard.** Before `:dev`/`:nightly` move, in the manifest job and before the Cloud Shell build, the published revision is compared with `github.sha`. `behind` skips the retag with a `::notice::`; an unknown revision proceeds.
- **Transitive-skip safety.** GitHub's implicit `success()` treats a skipped ancestor as not successful, and that could propagate into the reusable workflow's inner jobs. So the push caller has no skipped ancestor: the task asked for a single `test` job that `needs: pr-dedup`, and splitting it into `test` and `test-pr` is a deliberate deviation. `changes` needs `[test, test-pr]` and runs when either succeeded. `build`, `build-cloud-shell` and `manifest` state explicit `!cancelled()` plus result checks.
- **Contract tests.** `scripts/github-actions-contract.test.js` pins every new invariant, and `scripts/ci/*.test.js` tests the decision logic. Both run under `npm run test:orchestration`.
- **Rules and docs.**
  - `CLAUDE.md` gains a `## CI 파이프라인 성능 규정` section.
  - `ARCHITECTURE.md`, `backend/tests/TESTING.md` (including the missing `test-cloud-shell` entry) and `docs/testing.md` now describe the new pipeline.

## Measured levers (local CI-equivalent evidence)

- **Frontend 2-way `--shard`:** the larger shard ran 0.529 of the full suite, and all shards passed. The frontend job is the longest, so its halving shortens the critical path directly.
- **`pool: 'threads'`:** −14.8 % wall time, and 247/247 files passed twice.
- **Node environment for DOM-free files:** −9.4 %. The full two-project config passed 247/247. 62 files were measured passing under the node environment, and 57 were converted.
- **Backend `-n 4 --dist worksteal`:** about 2.1× faster wall time, with 0 failures in 38 local runs.
- **Removing `needs: version-check`:** saves about 14 s at the start of every test job.
- **Health interval 2 s:** removes most of the ~12.5 s health wait.

These are local measurements. Rule 1 of the new CI rules requires the before/after CI numbers from real runs before an effect is claimed. This change records the baseline, and the post-merge measurement is a follow-up.

## Rejected alternatives

- **`vitest --no-isolate`:** 111/105 files failed depending on order, and it ran out of memory. Module-state leakage between files makes global isolation removal unsafe. The new rules allow isolation removal only as a per-file opt-in after shuffled runs.
- **Path-based test skipping:** it saves only 0–5 s because every job's fixed cost remains. It also violates the `test.yml` policy that functional tests always run.
- **Self-hosted runners for PR code:** the repository is public and allows forks, so `pull_request` code on a self-hosted runner is a code-execution risk. A workflow `if:` can be edited by the PR, so the protection must also come from runner-group restrictions. PR builds stay on hosted runners, and the self-hosted image matrix stays non-PR.
- **`concurrency: cancel-in-progress` on push runs:** each dev push must publish its own images. Cancelling an in-progress push run would leave targets unbuilt; the carry-over gap this change fixes is the same class of problem. The stale re-run guard handles ordering instead.

## Capabilities

### Modified Capabilities

- CI test gate: parallel start, a sharded frontend, parallel backend unit tests, hermetic unit and contract layers, faster service readiness and PR dedup.
- Image publication: correct change detection, a published-revision basis, per-target manifests and a stale re-run guard.

## Impact

Affects:

- `.github/workflows/test.yml` and `.github/workflows/docker-build.yml`
- `scripts/ci/` (new), `scripts/github-actions-contract.test.js`, `scripts/test-target.test.js` and `package.json` (`test:orchestration`, `test:unit:backend`)
- `backend/pyproject.toml`, `backend/uv.lock` and `backend/tests/`
- `frontend/vitest.config.ts` and 57 frontend test docblocks
- `CLAUDE.md` (a symlink to `AGENTS.md`), `ARCHITECTURE.md`, `backend/tests/TESTING.md` and `docs/testing.md`

No application runtime code, API or deployment manifest changes. Existing images have no revision label, so the first dev push after merge uses the `event.before` basis for every target. The per-arch `:<base>-amd64` tags are intermediate and are still overwritten by any build, including a stale re-run. Only the final `:dev`/`:nightly` tags are guarded.
