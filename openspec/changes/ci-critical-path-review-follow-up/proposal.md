## Why

An independent review of the archived change `ci-critical-path-overhaul` (commit `e7e2cb1e`) found one high-severity defect and several smaller gaps in `.github/workflows/docker-build.yml`, `.github/workflows/test.yml` and `scripts/ci/`.

- **High: `test-pr` also ran on push and dispatch.** Its condition `!cancelled() && needs.pr-dedup.outputs.skip != 'true'` has a status function, so GitHub does not add the implicit `success()`. On push and dispatch `pr-dedup` is skipped, its `outputs.skip` is the empty string, and `'' != 'true'` is true. `test-pr` therefore ran on every push. The `changes` gate (`needs.test.result == 'success' || needs.test-pr.result == 'success'`) then let one caller's pass hide the other's failure. If the reusable workflow's inner jobs were transitively skipped instead, the gate could pass with nothing executed. The contract test pinned the faulty expression, and ARCHITECTURE.md, AGENTS.md and the workflow comments described behaviour the code did not have.
- **The stale re-run guard blocked rollbacks.** It skipped the retag whenever the published revision was a descendant of `github.sha`. That is judged by ancestry alone, so a force-push rollback of `dev` or `main` looked like a stale re-run and left `:dev`/`:nightly` on the image the rollback was meant to remove.
- **Registry failures silently disabled carry-over.** `readRevision` turned every inspect failure (auth, network, rate limit) into "no revision". The detector then used only the event basis and emitted no warning. The registry login step is `continue-on-error`.
- **The per-arch intermediate tag is shared across SHAs.** An older concurrent run that pushes `<base>-amd64` late makes the newer run's manifest verify fail, and `:dev` lags until the next push's carry-over.
- **Lower-severity gaps.**
  - `test-live` could start while `version-check` was failing.
  - The shard verifier accepted any `0 < ran < suite` count.
  - The detector computed an unused PR diff with the tip-only pattern.
  - The `changes` checkout persisted its token for PR code.
  - The network guard did not attribute attempts from background threads and did not cover UDP `sendto`.
  - The archived change left its post-merge measurement untracked.

## What Changes

- **Caller gating.**
  - `test-pr` runs only under `github.event_name == 'pull_request' && !cancelled() && needs.pr-dedup.outputs.skip != 'true'`.
  - `changes` ties each caller to its event: `(github.event_name != 'pull_request' && needs.test.result == 'success') || (github.event_name == 'pull_request' && needs.test-pr.result == 'success')`.
  - `scripts/github-actions-contract.test.js` pins both exact expressions and rejects a bare `||` between the two caller results.
- **Rollback-aware guard.**
  - The guard is now `image-revision.js guard <image> <sha> <repo> <tracked-ref>`. It reads the tip of the tracked branch with `gh api repos/<repo>/git/ref/heads/<branch>`.
  - The tracked ref is the branch the tag follows (`:dev`→`refs/heads/dev`, `:nightly`→`refs/heads/main`), not the run's ref. A `workflow_dispatch` from another branch also publishes `:dev`. Keying the guard to the run's ref would treat that dispatch's own tip as current and move `:dev` backward.
  - It skips the retag only when three things hold: the published revision differs from `sha`, the tracked tip is known and differs from `sha`, and compare reports `behind`.
  - A SHA that is the tracked tip, including after a force-push rollback, always publishes. Anything unknown proceeds with a `::warning::`.
  - "Compute final tags" emits `tracked_ref`, and the Cloud Shell guard sets `TRACKED_REF` next to `BRANCH_TAG`. The contract pins the mapping and the 4-argument form at both call sites.
  - Known limitation: if a run for the commit being rolled back is still in flight, it can finish after the rollback and republish, because compare(rollback, bad) is `ahead`. Cancel in-flight runs when rolling back.
- **Discriminated revision reads.**
  - `readRevision` returns one of three kinds: `present`, `absent` (not found, manifest unknown, name unknown, or no label) or `error` (anything else, including a malformed or disagreeing label).
  - `detect-build-targets.js` builds a target when its read is `error`, and emits `::warning::` annotations for those targets and for a failed `registry-login` step outcome.
  - Only the genuine bootstrap case (`absent`) falls back to the event basis.
- **Shared per-arch tag.** Documented as a known limitation with its concrete consequence in ARCHITECTURE.md and the workflow comment. A digest artifact handoff sits on the self-hosted path and cannot be exercised locally, so it is left as a follow-up task below.
- **`test-live`.** It now needs `version-check` and `test-cloud-shell` as well as every test layer. The test jobs still start at t=0.
- **Shard verifier.**
  - It asserts that the shard ran exactly the number of files that Vitest 4's `calculateShardRange` assigns: `floor(n/count)`, plus one for each of the first `n % count` shards.
  - The contract pins that `frontend/vitest.config.ts` has no `exclude`, `projects` or `workspace`.
- **Detector.** The PR diff computation is removed, and PRs make no git, registry or API calls. The `changes` checkout drops `fetch-depth: 2` and sets `persist-credentials: false`.
- **Network guard.** Each blocked entry records the attempting thread's name. UDP `sendto` to a non-loopback address is blocked in both the 2-argument and 3-argument forms.
- **Docs.** ARCHITECTURE.md `CI와 이미지 발행`, AGENTS.md (CLAUDE.md) `CI 파이프라인 성능 규정` rules 3, 8 and 9, `backend/tests/TESTING.md`, and the workflow comments now match the source.

### Review round 2

A second review of the change set found one medium and six low issues. It also named three extra items.

- **Medium.** The contract did not pin the default of the inline `pr-dedup` shell. Flipping its first `skip=false` to `skip=true` passed the whole suite, and every early return would then have skipped the tests of fork and dependabot PRs. The decision now lives in `scripts/ci/pr-dedup.js`. Fake-exec unit tests and a real-git test pin its behaviour, and the contract pins the workflow step that calls it.
- **Low, fixed in this change.**
  - Contracts now require the shard, verifier and guard steps to gate. They must carry no `if:`, `continue-on-error:` or `|| true`, and both guard `case` blocks must keep exact arms.
  - `changes` drops the unused `pull-requests: read`.
  - Unexpected event-basis failures in the image detector now emit `::warning::`.
  - The dedup notice links the head commit, and CI rule 9 tells the merger to confirm that the dev push run is green.
  - `pr-dedup` drops its job-level `continue-on-error`. Whether GitHub runs reusable-workflow inner jobs under a failed caller dependency is a post-merge check.
  - `helm-release.yml` no longer uses a tip-only diff. `scripts/ci/helm-publish-decision.js` reuses the detector's event basis.
- **Extra items.**
  - The frontend shard jobs pin Node 22. Node 26.3.1 was reproduced locally to break jsdom `localStorage` tests.
  - The AGENTS.md CI rules scope now covers every workflow and `scripts/ci/`.
  - This change stays open for the post-merge items.

### Review round 3

A third review found two medium and seven low issues.

- **Medium: dedup trusted tree identity alone.**
  - `pr-dedup` skipped `test-pr` whenever the merge tree equalled the dev head tree. It assumed a dev push run had tested that commit.
  - The push trigger's `paths-ignore` breaks that assumption. A dev push that touches only `.argocd-source-*.yaml` or the dev `kustomization.yaml` creates no push run, yet those files are `check_architecture.py` input. A stale ARCHITECTURE stamp could therefore reach `main` with only skipped tests.
  - The script now also requires a `docker-build.yml` push run for the head SHA, in any status, through the Actions runs API with `actions: read`. Zero runs or any API error runs the tests.
- **Medium: rule 10 had no contract.**
  - Moving a `test.yml` job or the `changes` job to self-hosted survived the suite. So did forcing `is_pr=false`, which would let the self-hosted, `packages: write` build run for PRs.
  - `build`, `build-cloud-shell` and `manifest` now start their `if` with `github.event_name != 'pull_request'`. A contract parses every workflow and enforces this for every non-hosted job. It requires GitHub-hosted `ubuntu-*` for PR-reachable jobs and for every `test.yml` job, bans `pull_request_target`, and pins the `is_pr` step.
- **Low, fixed.**
  - Both detector diffs use `--no-renames`, so a file moved out of an image directory, or out of `helm/afterglow/`, still counts at its source path.
  - `test.yml` layer steps are pinned as gating, with exact commands, and `test-live`'s `if` is pinned.
  - `test-pr` no longer inherits secrets.
  - The vitest comment labels its local measurement.
  - The ARCHITECTURE.md Code map lists `pr-dedup.js`, `helm-publish-decision.js` and `helm-release.yml`.
  - The post-merge tasks now measure the PR path (`pr-dedup` plus `test-pr`). The projected added latency is recorded and labelled as a projection.
- **Low, no change.** The first change was archived with two open post-merge tasks. They are carried here, and this change stays open until they are measured.

### Review round 4

A fourth review found one medium and nine low issues. It also clarified canonical rules 3 and 10.

- **Medium: nothing tested the network guard's teardown.** The teardown is the only thing that fails a non-hermetic test when app code swallows the blocked connect, and every guard test cleared the record before teardown. The guard now lives in `backend/tests/_network_guard.py`, and conftest imports it. A subprocess test loads it as a plugin and asserts that a swallowed connect and a swallowed DNS lookup each end in a teardown error.
- **Low, fixed.**
  - Rule 7 overclaimed. In CI (no `afterglow.conf`) a missing mock failed in DNS before `connect` and passed. The guard now also blocks host-name `getaddrinfo`, and rule 7 states that config loading is not isolated.
  - The shard verifier's failure-case test was vacuous for three of its four checks.
  - No contract kept secrets out of `pr-dedup` and `changes`.
  - The service health budget had no start period. CI now adds `--health-start-period 30s` with `--health-start-interval 2s`.
  - The rule 10 contract modelled only `pull_request`. `issue_comment`, `workflow_run`, review events and `merge_group` now count as PR-reachable, and they need an allow-list.
  - The archived proposal had no superseded note.
- **Low, documented or tracked, no code change.**
  - Dedup on existence rather than on the push run's result is an accepted trade-off, documented in ARCHITECTURE.md.
  - The `pr-dedup` pre-gate is now named in rule 3 as a documented exception. Its latency measurement stays a post-merge task.
  - The shared per-arch tag race stays a post-merge decision.
- **Canonical rule alignment.**
  - Rule 3: only publishes and deploys are gated on the whole test result, so PR verification builds that publish nothing may run in parallel. `helm-release.yml` and `docs.yml` are recorded as current exceptions, with a follow-up task.
  - Rule 10 keeps the YAML guards and adds the settings-level controls. The repository is org-owned, and the runner-group state was unreadable, so both controls are recorded as owner actions with their exact settings paths.

## Impact

Affects:

- `.github/workflows/docker-build.yml`, `.github/workflows/test.yml` and `.github/workflows/helm-release.yml`
- `frontend/vitest.config.ts` (comment only)
- `scripts/ci/detect-build-targets.js`, `scripts/ci/image-revision.js`, `scripts/ci/verify-vitest-shard.js`, `scripts/ci/pr-dedup.js` and `scripts/ci/helm-publish-decision.js`, with their tests
- `package.json` `test:orchestration` and its pin in `scripts/test-target.test.js`
- `scripts/github-actions-contract.test.js`
- `backend/tests/conftest.py`, `backend/tests/_network_guard.py` and `backend/tests/test_network_guard.py`
- `ARCHITECTURE.md`, `AGENTS.md`, `backend/tests/TESTING.md`, `docs/testing.md` and the archived `2026-09-23-ci-critical-path-overhaul/proposal.md` (note only)

There is no application runtime, API, schema, configuration or deployment manifest change. The post-merge items stay open in this change, because they need real GitHub Actions runs.
