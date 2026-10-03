# Agent CI Safety Specification

## Purpose

Guide changes to all `.github/workflows/`, `scripts/ci/` and their tests without turning historical timing observations into permanent requirements. `ARCHITECTURE.md`'s CI and image publication sections and actual workflow/contracts describe the current implementation.

## Requirements

### Requirement: CI changes have comparable measured evidence
Before and after CI changes the agent SHALL gather job/step durations for at least 20 comparable runs when available, record sample sizes, critical-path median and p90, and optimize the last/longest required job rather than adding speculative per-step savings. Public hosted runner work prioritizes wall-clock; private/paid runners require cost comparison as well. Unobserved improvement SHALL be labelled projection. Cache restoration, checkout, installation and service startup are measured as per-job overhead; do not retain a cache that is slower than reinstalling. Re-measure when the median worsens by >=20%, the suite grows substantially, or a new test layer is added. Historical 2026-09 baselines (e.g. 143s median and 155s p90) are dated references, not current CI pass criteria.

#### Scenario: A shard is proposed to save time
- **WHEN** a workflow is split into new parallel jobs
- **THEN** the agent measures fixed overhead and confirms actual per-shard test/file counts before claiming a critical-path gain

### Requirement: Required tests gate publication without serializing unrelated checks
Fail-fast version/document/architecture checks SHALL run in parallel with tests, not as their `needs`. Publishing images/packages or deploying SHALL wait for the entire applicable test gate; a non-publishing PR validation build MAY run beside tests. A workflow exception (currently separate Helm chart and docs publishing) SHALL be documented as an exception, not misrepresented as gated. The `test-pr` caller runs only for PRs; a push caller and PR caller SHALL have event-specific result checks, so either passing result cannot hide the other's failure. `test-live` remains opt-in and waits for version and required test layers. Skipped jobs and empty outputs SHALL NOT be treated as `success` by implicit status functions.

#### Scenario: A PR-only job is skipped on push
- **WHEN** a push run reaches the image publication gate
- **THEN** only that push's completed test caller can permit publication, never an empty PR caller output

### Requirement: Automated promotion PRs receive a real required test run
`promote-kolla-role-tags.yml` opens `automation/kolla-role-tags` PRs using `GITHUB_TOKEN`, whose pushes and PR creation do not trigger ordinary GitHub Actions workflows. Before merging such a PR, the maintainer SHALL close/reopen it to create a human-triggered PR run and SHALL verify the checked head still equals the final PR head after any subsequent hourly force-push. `docker-build.yml` `workflow_dispatch` SHALL NOT substitute for this check: on that ref it can publish `dev`-family image tags. Changing to a GitHub App or PAT is a separate owner-approved action.

#### Scenario: The automation updates a PR after its test
- **WHEN** `automation/kolla-role-tags` force-pushes a new head after its PR checks ran
- **THEN** the maintainer causes new PR checks for the final head before merging, instead of dispatching a publishing workflow

### Requirement: Detection, deduplication and revision checks are fail-safe
Push changes SHALL compare `github.event.before..github.sha` without rename detection; zero SHA, forced push or missing diff basis triggers full evaluation with appropriate warnings for unexpected errors. PRs compare base to head where relevant; last-commit-only `HEAD^1..HEAD` is not a push basis. Image decisions SHALL consider the actual published revision. Registry read errors SHALL warn and rebuild instead of masquerading as absent images. A stale re-run SHALL NOT retag an older commit over a newer tracked branch tip; a tracked-tip rollback SHALL still publish. PR test deduplication requires a same-repo `dev` branch, identical merge/head trees, and an existing push workflow run for that head SHA; fork/dependabot PRs or lookup errors SHALL run tests. Mergers SHALL check that the referenced push run actually passed for the final head.

#### Scenario: Registry inspection is unavailable
- **WHEN** authentication, network or rate limiting prevents reading the published revision
- **THEN** the detector emits a warning and rebuilds affected targets instead of assuming no revision exists

### Requirement: Parallel tests remain hermetic and accounted for
Unit/contract tests SHALL NOT call external Keystone/OpenStack/Prometheus or external DNS. `backend/tests/_network_guard.py` blocks non-loopback TCP/UDP and external hostname resolution even when application code swallows exceptions; tests restoring global state SHALL clean up. Workers are bounded to CI vCPU (`pytest -n 4`, never `-n auto`). A shard SHALL invoke the real runner directly, verify executed file count and disjoint coverage, and not quietly run the full suite because a wrapper dropped `--shard`. Isolation SHALL be disabled only on explicitly verified safe test files after shuffled runs.

#### Scenario: A test silently catches a blocked network call
- **WHEN** a unit test triggers an external DNS or connect that code swallows
- **THEN** teardown reports a hermeticity failure rather than allowing the suite to pass

### Requirement: Public PR code stays away from privileged execution
Untrusted PR code SHALL NOT run on self-hosted runners or with publication credentials. PR-reachable jobs and reusable test jobs SHALL use hosted `ubuntu-*`; non-hosted jobs need a top-level event guard excluding every PR-reachable trigger. `pull_request_target` SHALL NOT execute PR code. An owner SHALL also restrict runner-group repository access and fork approval settings; YAML alone can be changed by a PR and is not the whole security boundary. The agent SHALL NOT change org/repository settings without owner authorization. `scripts/github-actions-contract.test.js`, `scripts/test-target.test.js`, and `scripts/ci/*.test.js` SHALL protect the relevant gates, commands, triggers and skip criteria; update contracts intentionally with a CI change, not by weakening them.

2026-09-24의 읽기 전용 조회에서 repository-level self-hosted runner는 0개였고 fork PR 승인값은 `first_time_contributors`였다. Organization runner group은 권한 부족(HTTP 403)으로 확인하지 못했다. Org owner는 Organization Settings → Actions → Runner groups에서 public 저장소 접근 범위를 확인·제한하고, repo admin은 Settings → Actions → General에서 외부 기여자 승인 정책을 검토한다. 조회 결과는 현재 설정을 증명하지 않으며, 설정 변경은 별도 승인 작업이다.

#### Scenario: A workflow introduces a runner matrix
- **WHEN** a PR-reachable job switches from a hosted literal to an expression or self-hosted runner
- **THEN** publication is blocked until the PR path is explicitly excluded and owner-controlled runner restrictions are confirmed
