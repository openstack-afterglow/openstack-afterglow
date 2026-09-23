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

## Impact

Affects:

- `.github/workflows/docker-build.yml` and `.github/workflows/test.yml`
- `scripts/ci/detect-build-targets.js`, `scripts/ci/image-revision.js` and `scripts/ci/verify-vitest-shard.js`, with their tests
- `scripts/github-actions-contract.test.js`
- `backend/tests/conftest.py` and `backend/tests/test_network_guard.py`
- `ARCHITECTURE.md`, `AGENTS.md` and `backend/tests/TESTING.md`

There is no application runtime, API, schema, configuration or deployment manifest change. The post-merge items stay open in this change, because they need real GitHub Actions runs.
