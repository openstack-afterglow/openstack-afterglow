const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const test = require("node:test")

const rootDir = path.resolve(__dirname, "..")
const claudeWorkflow = fs.readFileSync(path.join(rootDir, ".github", "workflows", "claude.yml"), "utf8")

test("Claude workflow accepts explicit conversation mentions without automated review triggers", () => {
	assert.match(claudeWorkflow, /^  issue_comment:\s*$/m)
	assert.match(claudeWorkflow, /^  issues:\s*$/m)
	assert.match(claudeWorkflow, /github\.event_name == 'issue_comment'.*'@claude'/)
	assert.match(claudeWorkflow, /github\.event_name == 'issues'.*'@claude'/)

	assert.doesNotMatch(claudeWorkflow, /^  pull_request_review:\s*$/m)
	assert.doesNotMatch(claudeWorkflow, /^  pull_request_review_comment:\s*$/m)
	assert.doesNotMatch(claudeWorkflow, /github\.event_name == 'pull_request_review(?:_comment)?'/)
})

// ─── CI 크리티컬 패스·이미지 발행 불변식 (CLAUDE.md "CI 파이프라인 성능 규정" 11번) ─────────────
const testWorkflow = fs.readFileSync(path.join(rootDir, ".github", "workflows", "test.yml"), "utf8")
const dockerWorkflow = fs.readFileSync(path.join(rootDir, ".github", "workflows", "docker-build.yml"), "utf8")

/** `jobs:` 아래 2칸 들여쓴 job 블록을 다음 job 시작 전까지 잘라낸다. */
function jobBlock(workflow, name) {
	const start = workflow.indexOf(`\n  ${name}:\n`)
	assert.ok(start >= 0, `job ${name} must exist`)
	const rest = workflow.slice(start + 1)
	const next = rest.slice(1).search(/\n  [A-Za-z0-9_-]+:\n/)
	return next < 0 ? rest : rest.slice(0, next + 1)
}

/** job 블록 안에서 `- name: <name>` step 블록을 다음 step 시작 전까지 잘라낸다. */
function stepBlock(job, name) {
	const start = job.indexOf(`- name: ${name}`)
	assert.ok(start >= 0, `step ${name} must exist`)
	const rest = job.slice(start)
	const next = rest.slice(1).search(/\n\s+- (name|uses):/)
	return next < 0 ? rest : rest.slice(0, next + 1)
}

/** step 의 `run: |` literal block(키 줄 + 키보다 깊게 들여쓴 줄). 뒤따르는 주석·다음 job 은 포함하지 않는다. */
function runBlock(step) {
	const lines = step.split("\n")
	const start = lines.findIndex((line) => /^\s+run: \|\s*$/.test(line))
	assert.ok(start >= 0, "step must have a run: | block")
	const keyIndent = lines[start].search(/\S/)
	const body = []
	for (const line of lines.slice(start + 1)) {
		if (line.trim() !== "" && line.search(/\S/) <= keyIndent) break
		body.push(line)
	}
	return [lines[start].trim(), ...body].join("\n").trimEnd()
}

/** job 블록의 `    if: ...` 한 줄 값. */
function jobIf(job) {
	const match = /^    if: (.+)$/m.exec(job)
	assert.ok(match, "job must declare an if")
	return match[1].trim()
}

test("test jobs start at t=0: no test job waits on version-check", () => {
	assert.match(testWorkflow, /^  version-check:\s*$/m)
	for (const job of ["test-backend", "test-cloud-shell", "test-contract", "test-functional", "test-frontend", "detect-live"]) {
		const block = jobBlock(testWorkflow, job)
		assert.doesNotMatch(block, /^\s+needs:/m, `${job} must start at t=0 without needs`)
	}
	// 빌드 게이팅은 docker-build.yml changes 가 reusable test workflow 전체에 걸어 유지한다.
	const changes = jobBlock(dockerWorkflow, "changes")
	assert.match(changes, /^    needs: \[test, test-pr\]\s*$/m)
})

test("the build gate ties each test caller's result to its own event", () => {
	const changes = jobIf(jobBlock(dockerWorkflow, "changes"))
	assert.equal(
		changes,
		"${{ !cancelled() && ((github.event_name != 'pull_request' && needs.test.result == 'success') || (github.event_name == 'pull_request' && needs.test-pr.result == 'success')) }}",
	)
	// 한 caller 의 통과가 다른 caller 의 실패를 가리는 `a || b` 결합은 금지한다.
	assert.doesNotMatch(changes, /\|\|\s*needs\.test-pr\.result == 'success'/)
	assert.doesNotMatch(changes, /needs\.test\.result == 'success'\s*\|\|/)
})

test("functional tests always run and live tests wait on version-check and every test layer", () => {
	assert.doesNotMatch(jobBlock(testWorkflow, "test-functional"), /^    if:/m)
	const needs = /^    needs: \[([^\]]+)\]\s*$/m.exec(jobBlock(testWorkflow, "test-live"))
	assert.ok(needs, "test-live must declare needs")
	assert.deepEqual(
		needs[1].split(",").map((name) => name.trim()).sort(),
		["detect-live", "test-backend", "test-cloud-shell", "test-contract", "test-frontend", "test-functional", "version-check"],
	)
})

/** step 이 조건 없이 실행되고 실패가 잡을 실패시키는지(`if:`·`continue-on-error:`·`|| true` 없음). */
function assertGatingStep(step, label) {
	assert.doesNotMatch(step, /^\s+if:/m, `${label} must not be conditional`)
	assert.doesNotMatch(step, /^\s+continue-on-error:/m, `${label} must fail its job`)
	assert.doesNotMatch(step, /\|\|\s*(true\b|:(?=\s|$))/m, `${label} must not swallow its exit code`)
}

test("every test layer step gates its job and runs exactly its pinned command", () => {
	// CI 규정 11번: 안전 단계는 존재만이 아니라 게이트하는지도 고정한다. `|| true` 만이 무력화 방법은 아니므로
	// (예: `run: "true"`, 다른 명령) step 의 run 줄도 정확히 고정한다.
	const gating = {
		"version-check": [
			["Check architecture freshness", "python3 scripts/check_architecture.py"],
			["Test target orchestration", "npm run test:orchestration"],
			["Check versions aligned", "bash scripts/check-version-sync.sh"],
		],
		"test-backend": [
			["Sync deps (dev)", "uv sync --frozen --extra dev"],
			["Lint ruff check", "uv run ruff check ."],
			["Lint ruff format check", "uv run ruff format --check ."],
			["Unit tests", "npm run test:unit:backend"],
		],
		"test-cloud-shell": [["Image and bootstrap smoke", "npm run test:cloud-shell:image"]],
		"test-contract": [
			["Sync deps (dev)", "uv sync --frozen --extra dev"],
			["Contract tests", "npm run test:contract"],
			["Kolla contract tests", "npm run test:kolla:contract"],
		],
		"test-functional": [
			["Sync deps (dev)", "uv sync --frozen --extra dev"],
			["Functional tests", "npm run test:functional -- --no-start"],
		],
		"test-frontend": [["Install", "bun install --frozen-lockfile"]],
		"test-live": [["Live OpenStack tests", "npm run test:live"]],
	}
	for (const [jobName, steps] of Object.entries(gating)) {
		const job = jobBlock(testWorkflow, jobName)
		// 필수 계층 잡은 조건 없이 실행된다. opt-in 인 test-live 의 if 는 아래에서 정확히 고정한다.
		if (jobName !== "test-live") assert.doesNotMatch(job, /^    if:/m, `${jobName} must not be conditional`)
		assert.doesNotMatch(job, /^    continue-on-error:/m, `${jobName} must fail the workflow`)
		for (const [name, command] of steps) {
			const step = stepBlock(job, name)
			assertGatingStep(step, `${jobName} "${name}"`)
			const runs = (step.match(/^\s+run:.*$/gm) || []).map((line) => line.trim())
			assert.deepEqual(runs, [`run: ${command}`], `${jobName} "${name}" must run exactly ${command}`)
		}
	}
	// architecture freshness 는 version-check 의 첫 명령이다(tag-only version 처리보다 먼저).
	const versionCheck = jobBlock(testWorkflow, "version-check")
	assert.ok(versionCheck.indexOf("Check architecture freshness") < versionCheck.indexOf("- uses: actions/setup-node@v4"))

	// 실제 자격 증명을 쓰는 test-live 는 status 함수 없이(암묵적 success()) detect-live 결과만 본다.
	// always()·!cancelled() 가 붙으면 version-check 나 테스트 계층이 실패해도 live 테스트가 돈다.
	assert.equal(jobIf(jobBlock(testWorkflow, "test-live")), "${{ needs.detect-live.outputs.enabled == 'true' }}")
})

test("frontend runs as a verified 2-way vitest shard matrix", () => {
	const job = jobBlock(testWorkflow, "test-frontend")
	assert.match(job, /name: Frontend \(unit tests \$\{\{ matrix\.shard \}\}\/2\)/)
	assert.match(job, /strategy:\s+fail-fast: false\s+matrix:\s+shard: \[1, 2\]/)
	// 잡 자체도 조건 없이 실행되고 실패를 드러낸다.
	assert.doesNotMatch(job, /^    if:/m, "test-frontend must not be conditional")
	assert.doesNotMatch(job, /^    continue-on-error:/m, "test-frontend must fail the workflow")

	// vitest bin(`#!/usr/bin/env node`)과 검증기는 setup-node 의 Node 22 로 실행한다. Node 25+ 의 내장
	// Web Storage 가 jsdom 테스트와 충돌하므로 runner image 의 기본 Node 에 맡기지 않는다.
	const setupNode = job.match(/- uses: actions\/setup-node@v4\n\s+with:\n\s+node-version: "22"\n/g) || []
	assert.equal(setupNode.length, 1, "test-frontend pins Node 22 once")
	assert.equal((job.match(/actions\/setup-node@/g) || []).length, 1)
	assert.ok(job.indexOf("actions/setup-node@v4") < job.indexOf("Test (vitest shard"), "Node is set up before vitest runs")
	const versionCheckNode = /- uses: actions\/setup-node@v4\n\s+with:\n\s+node-version: "(\d+)"/.exec(jobBlock(testWorkflow, "version-check"))
	assert.ok(versionCheckNode, "version-check sets up Node")
	assert.equal(versionCheckNode[1], "22", "frontend shards use the same Node major as version-check")

	// 래퍼(npm run/npm test) 뒤의 `-- --shard` 는 인자가 전달되지 않으므로 vitest 를 직접 호출한다.
	const run = stepBlock(job, "Test (vitest shard")
	assertGatingStep(run, "vitest shard step")
	assert.match(run, /\.\/node_modules\/\.bin\/vitest run/)
	assert.match(run, /--shard=\$\{\{ matrix\.shard \}\}\/2/)
	assert.match(run, /--reporter=json/)
	assert.match(run, /--reporter=github-actions/)
	const report = /--outputFile\.json=(\S+)/.exec(run)
	assert.ok(report, "vitest must write a JSON report")
	assert.doesNotMatch(job, /npm run test:unit:frontend|run: npm test/)

	const verify = stepBlock(job, "Verify shard file count")
	assertGatingStep(verify, "shard verifier step")
	assert.match(verify, /node \.\.\/scripts\/ci\/verify-vitest-shard\.js/)
	assert.ok(verify.includes(`--report ${report[1]}`), "verifier must read the report vitest wrote")
	assert.match(verify, /--shard \$\{\{ matrix\.shard \}\}\/2/)
	assert.ok(job.indexOf("Verify shard file count") > job.indexOf("Test (vitest shard"))

	const helper = stepBlock(job, "Test runner log helper (shard 1 only)")
	assert.match(helper, /if: matrix\.shard == 1/)
	assert.match(helper, /run: node --test scripts\/run-with-file-log\.test\.mjs/)

	// frontend `npm test` 가 바뀌면 CI 가 그 단계를 빠뜨리지 않도록 함께 갱신해야 한다.
	const frontendPkg = JSON.parse(fs.readFileSync(path.join(rootDir, "frontend", "package.json"), "utf8"))
	assert.equal(frontendPkg.scripts.test, "vitest run && node --test scripts/run-with-file-log.test.mjs")
	const vitestConfig = fs.readFileSync(path.join(rootDir, "frontend", "vitest.config.ts"), "utf8")
	assert.match(vitestConfig, /include: \['src\/\*\*\/\*\.\{test,spec\}\.\{js,ts\}'\]/)
	// verify-vitest-shard.js 는 include 패턴으로 스위트를 세고 vitest 분할 크기와 정확히 비교한다.
	// exclude/projects/workspace 가 생기면 두 수가 달라지므로 검증기를 함께 바꿔야 한다.
	assert.doesNotMatch(vitestConfig, /\b(exclude|projects|workspace)\s*:/)
})

test("service containers use the dev compose test-profile health timing plus a CI start period", () => {
	const values = (flag) => Array.from(testWorkflow.matchAll(new RegExp(`--${flag}[= ](\\S+)`, "g")), (m) => m[1])
	// mariadb, postgres, functional redis, live redis. 각 flag 는 service 마다 정확히 한 번이다.
	for (const [flag, value] of [
		["health-interval", "2s"],
		["health-timeout", "5s"],
		["health-retries", "20"],
		// CI service 는 tmpfs 가 아니므로 cold init 예산을 늘린다. start-period 동안의 실패는 retries 에 세지 않는다.
		["health-start-period", "30s"],
		// Docker 25+ 는 start-period 동안 start-interval(기본 5초)로 검사한다. 2s 로 두어 정상 경로를 늦추지 않는다.
		["health-start-interval", "2s"],
	]) {
		assert.deepEqual(values(flag), [value, value, value, value], flag)
	}

	const compose = fs.readFileSync(path.join(rootDir, "docker-compose.dev.yml"), "utf8")
	for (const service of ["mariadb", "postgres", "test-redis"]) {
		const start = compose.indexOf(`\n  ${service}:\n`)
		assert.ok(start >= 0, `compose ${service} must exist`)
		const block = compose.slice(start, start + 1200)
		assert.match(block, /interval: 2s\s+timeout: 5s\s+retries: 20/, `compose ${service} health timing`)
	}
})

test("PR dedup skips only same-repo dev PRs whose merge tree equals the head tree and whose push run exists", () => {
	const job = jobBlock(dockerWorkflow, "pr-dedup")
	assert.match(job, /^    if: github\.event_name == 'pull_request'\s*$/m)
	assert.match(job, /runs-on: ubuntu-latest/)
	// actions: read 는 head SHA 의 docker-build.yml push 실행 조회용이다. 쓰기 권한은 없다.
	assert.match(
		job,
		/^    permissions:\n      contents: read\n      actions: read\n    outputs:\n      skip: \$\{\{ steps\.dedup\.outputs\.skip \}\}\n/m,
	)
	// 판단 step 은 항상 성공하므로 job-level continue-on-error 는 인프라 실패만 가린다. 실패는 red 로 드러낸다.
	assert.doesNotMatch(job, /^    continue-on-error:/m, "pr-dedup must not hide its own failure")

	// checkout 실패는 다음 step 의 fallback 이 skip=false 로 처리한다.
	const checkout = stepBlock(job, "Checkout PR merge commit")
	assert.match(checkout, /continue-on-error: true/)
	assert.match(checkout, /persist-credentials: false/)

	const dedup = stepBlock(job, "Compare trees and find the push run")
	assert.match(dedup, /id: dedup/)
	assert.match(dedup, /^          GH_TOKEN: \$\{\{ github\.token \}\}$/m)
	assert.match(dedup, /HEAD_REPO: \$\{\{ github\.event\.pull_request\.head\.repo\.full_name \}\}/)
	assert.match(dedup, /BASE_REPO: \$\{\{ github\.repository \}\}/)
	assert.match(dedup, /HEAD_REF: \$\{\{ github\.head_ref \}\}/)
	assert.match(dedup, /HEAD_SHA: \$\{\{ github\.event\.pull_request\.head\.sha \}\}/)
	assert.match(dedup, /PR_AUTHOR: \$\{\{ github\.event\.pull_request\.user\.login \}\}/)

	// 규칙은 scripts/ci/pr-dedup.js(단위·실제 git 테스트)가 소유한다. step 은 스크립트를 부르고, 스크립트를 실행하지
	// 못하면 skip=false 를 쓴다. 공격자가 정하는 값은 env 로만 전달한다(쉘 보간 금지).
	const run = runBlock(dedup)
	assert.doesNotMatch(run, /\$\{\{/)
	assert.equal(
		run,
		[
			"run: |",
			"          node scripts/ci/pr-dedup.js || {",
			'            echo "::warning title=PR dedup::pr-dedup.js did not complete; running Layered Tests"',
			'            echo "skip=false" >> "$GITHUB_OUTPUT"',
			"          }",
		].join("\n"),
	)
	// workflow 어디에도 skip=true 를 쓰는 경로가 없다(인라인 판단으로 되돌리며 기본값을 뒤집는 회귀 방지).
	assert.doesNotMatch(dockerWorkflow, /skip=true/)
	assert.equal((job.match(/GITHUB_OUTPUT/g) || []).length, 1, "the workflow writes only the skip=false fallback")
	// 실행 존재 확인은 이 workflow 파일의 push 실행을 조회한다(정확한 argv 는 pr-dedup.test.js 가 고정한다).
	const dedupScript = fs.readFileSync(path.join(rootDir, "scripts", "ci", "pr-dedup.js"), "utf8")
	assert.match(dedupScript, /const PUSH_WORKFLOW = "docker-build\.yml";/)
	assert.match(dedupScript, /actions\/workflows\/\$\{PUSH_WORKFLOW\}\/runs\?head_sha=\$\{headSha\}&event=push&per_page=100/)

	// push/dispatch caller 에는 skipped 조상이 없어야 한다(암묵적 success() 가 내부 잡을 건너뛰지 않도록).
	const testJob = jobBlock(dockerWorkflow, "test")
	assert.doesNotMatch(testJob, /^    needs:/m)
	assert.match(testJob, /^    if: github\.event_name != 'pull_request'\s*$/m)
	assert.match(testJob, /uses: \.\/\.github\/workflows\/test\.yml/)
	// push/dispatch caller 만 opt-in live 테스트용 secrets 를 넘긴다.
	assert.match(testJob, /^    secrets: inherit\s*$/m)

	// test-pr 는 status 함수(!cancelled())를 쓰므로 암묵적 success() 가 없다. push/dispatch 에서 skipped 인
	// pr-dedup 의 outputs.skip 은 '' 이므로 event 조건이 맨 앞에서 PR 이외 이벤트를 막아야 한다.
	const prTestJob = jobBlock(dockerWorkflow, "test-pr")
	assert.match(prTestJob, /^    needs: pr-dedup\s*$/m)
	assert.equal(
		jobIf(prTestJob),
		"${{ github.event_name == 'pull_request' && !cancelled() && needs.pr-dedup.outputs.skip != 'true' }}",
	)
	assert.match(prTestJob, /uses: \.\/\.github\/workflows\/test\.yml/)
	assert.match(prTestJob, /run_live_openstack: false/)
	// PR 코드를 실행하는 caller 는 live 를 끄므로 저장소 secrets 를 reusable workflow 에 넘기지 않는다.
	assert.doesNotMatch(prTestJob, /^    secrets:/m, "test-pr must not pass repository secrets")
})

/** `#` 주석 줄을 뺀 블록. 주석의 secrets 설명은 참조가 아니다. */
function withoutComments(block) {
	return block
		.split("\n")
		.filter((line) => !/^\s*#/.test(line))
		.join("\n")
}

// `${{ secrets.X }}`, `secrets['X']`, `toJSON(secrets)`. 단어 secrets 만으로는 매치하지 않는다.
const SECRETS_REF = /\bsecrets\s*[.[]|toJSON\(\s*secrets\s*\)/

test("jobs that run PR code reference no secrets outside the push-only registry login", () => {
	// pr-dedup 과 changes 는 PR 이벤트에서 PR 코드(scripts/ci/*.js)를 실행한다(CI 규정 10번).
	assert.doesNotMatch(withoutComments(jobBlock(dockerWorkflow, "pr-dedup")), SECRETS_REF, "pr-dedup must not reference secrets")
	const changes = jobBlock(dockerWorkflow, "changes")
	const login = stepBlock(changes, "Log in to registry (push only, read published revisions)")
	assert.match(login, /^        if: github\.event_name == 'push'$/m)
	assert.match(withoutComments(login), SECRETS_REF, "sanity: the push-only login step holds the registry secrets")
	assert.doesNotMatch(
		withoutComments(changes.replace(login, "")),
		SECRETS_REF,
		"changes may reference secrets only in the push-only registry login step",
	)
	// workflow-level env 는 PR 잡에도 상속된다. 허용하는 secrets 참조는 레지스트리 host(자격 증명 아님) 하나뿐이다.
	const env = /^env:\n((?: {2}.*\n|\s*\n)*)/m.exec(dockerWorkflow)
	assert.ok(env, "docker-build.yml must declare a workflow-level env")
	assert.deepEqual(
		withoutComments(env[1]).split("\n").filter((line) => SECRETS_REF.test(line)),
		["  REGISTRY: ${{ secrets.REGISTRY_URL || 'ghcr.io' }}"],
	)
})

test("image target detection diffs event.before on push, never only the tip commit", () => {
	const job = jobBlock(dockerWorkflow, "changes")
	assert.doesNotMatch(dockerWorkflow, /git diff --name-only HEAD\^1 HEAD/)
	assert.doesNotMatch(job, /fetch-depth:/, "no HEAD^1 comparison needs a second commit")
	assert.match(job, /EVENT_BEFORE: \$\{\{ github\.event\.before \}\}/)
	assert.match(job, /EVENT_FORCED: \$\{\{ github\.event\.forced \}\}/)
	assert.match(job, /run: node scripts\/ci\/detect-build-targets\.js/)
	for (const output of ["targets", "standard_targets", "effective_ref", "cloud_shell", "is_pr"]) {
		assert.match(job, new RegExp(`^      ${output}: \\$\\{\\{ steps\\.`, "m"), `changes output ${output}`)
	}

	// 레지스트리 자격 증명과 compare 토큰은 push 에서만 사용한다(PR 코드가 이 job 을 실행한다).
	// checkout 토큰도 .git/config 에 남기지 않는다.
	assert.match(stepBlock(job, "Checkout"), /persist-credentials: false/)
	// is_pr 는 build 의 보조 PR 제외와 build-push 의 push 여부를 정한다. 항상 false 를 쓰는 회귀를 막는다.
	assert.equal(
		runBlock(stepBlock(job, "Resolve effective ref")),
		[
			"run: |",
			'          echo "ref=$GITHUB_REF" >> $GITHUB_OUTPUT',
			'          if [[ "$GITHUB_EVENT_NAME" == "pull_request" ]]; then',
			'            echo "is_pr=true" >> $GITHUB_OUTPUT',
			"          else",
			'            echo "is_pr=false" >> $GITHUB_OUTPUT',
			"          fi",
		].join("\n"),
	)
	const login = stepBlock(job, "Log in to registry (push only")
	assert.match(login, /id: registry-login/)
	assert.match(login, /if: github\.event_name == 'push'/)
	assert.match(job, /REGISTRY_LOGIN_OUTCOME: \$\{\{ steps\.registry-login\.outcome \}\}/)
	assert.match(job, /GH_TOKEN: \$\{\{ github\.event_name == 'push' && github\.token \|\| '' \}\}/)
	// 최소 권한: PR diff 를 계산하지 않으므로 pull-requests 권한이 없다. packages: read 는 push 의 발행 revision 조회용이다.
	assert.match(job, /^    permissions:\n      contents: read\n      packages: read\n    outputs:\n/m)
	assert.doesNotMatch(job, /pull-requests:/)

	const detect = fs.readFileSync(path.join(rootDir, "scripts", "ci", "detect-build-targets.js"), "utf8")
	assert.match(detect, /env\.EVENT_BEFORE/)
	assert.match(detect, /"fetch", "--no-tags", "--depth=1", "origin", before/)
	// rename 감지가 켜져 있으면 이미지 디렉터리 밖으로 옮긴 파일이 도착 경로로만 보고된다. 두 diff 를 따로 고정한다.
	assert.match(detect, /exec\("git", \["diff", "--no-renames", "--name-only", before, head\]\)/)
	assert.match(detect, /exec\("git", \["diff", "--no-renames", "--name-only", revision, sha\]\)/)
	assert.equal((detect.match(/exec\("git", \["diff"/g) || []).length, 2, "the detector has exactly two git diff calls")
	assert.ok(!detect.includes("HEAD^1"), "the detector must not keep a tip-only first-parent diff")
	assert.match(detect, /env\.REGISTRY_LOGIN_OUTCOME === "failure"/)
})

const workflowDir = path.join(rootDir, ".github", "workflows")
const allWorkflows = fs
	.readdirSync(workflowDir)
	.filter((name) => /\.ya?ml$/.test(name))
	.map((name) => [name, fs.readFileSync(path.join(workflowDir, name), "utf8")])

test("no workflow or CI script decides changes from the tip commit alone", () => {
	// CI 규정 8번: push 는 github.event.before..github.sha 로 비교한다. 마지막 커밋만 보는 비교는 금지한다.
	const tipOnly = /HEAD\^1?(?=[\s.'"]|$)|HEAD~1\b/m
	assert.ok(allWorkflows.length >= 7)
	for (const [name, text] of allWorkflows) assert.doesNotMatch(text, tipOnly, name)
	const ciDir = path.join(rootDir, "scripts", "ci")
	for (const name of fs.readdirSync(ciDir).filter((file) => file.endsWith(".js") && !file.endsWith(".test.js"))) {
		assert.doesNotMatch(fs.readFileSync(path.join(ciDir, name), "utf8"), tipOnly, `scripts/ci/${name}`)
	}
})

test("the Helm chart publish decision diffs event.before on main pushes and fails safe", () => {
	const helmWorkflow = fs.readFileSync(path.join(workflowDir, "helm-release.yml"), "utf8")
	const job = jobBlock(helmWorkflow, "check-changes")
	assert.doesNotMatch(job, /fetch-depth:/, "no tip-only comparison needs a second commit")
	assert.match(job, /^    permissions:\n      contents: read\n    outputs:\n      should_publish: \$\{\{ steps\.decide\.outputs\.publish \}\}\n/m)
	const decide = stepBlock(job, "Decide whether to publish")
	assert.match(decide, /id: decide/)
	assert.match(decide, /EVENT_BEFORE: \$\{\{ github\.event\.before \}\}/)
	assert.match(decide, /EVENT_FORCED: \$\{\{ github\.event\.forced \}\}/)
	assert.match(decide, /run: node scripts\/ci\/helm-publish-decision\.js\n/)
	assertGatingStep(decide, "helm publish decision")
	assert.match(jobBlock(helmWorkflow, "helm-publish"), /^    if: needs\.check-changes\.outputs\.should_publish == 'true'\s*$/m)

	// event 기준과 fail-safe 는 이미지 target 감지와 같은 구현을 쓴다.
	const helper = fs.readFileSync(path.join(rootDir, "scripts", "ci", "helm-publish-decision.js"), "utf8")
	assert.match(helper, /const \{ collectEventChanges \} = require\("\.\/detect-build-targets\.js"\)/)
	assert.match(helper, /const CHART_PATH = \/\^helm\\\/afterglow\\\/\//)
})

test("every scripts/ci test runs in test:orchestration", () => {
	const orchestration = JSON.parse(fs.readFileSync(path.join(rootDir, "package.json"), "utf8")).scripts["test:orchestration"]
	const ciTests = fs.readdirSync(path.join(rootDir, "scripts", "ci")).filter((name) => name.endsWith(".test.js"))
	assert.ok(ciTests.length >= 5)
	for (const name of ciTests) assert.ok(orchestration.includes(`scripts/ci/${name}`), `test:orchestration must run scripts/ci/${name}`)
})

test("every image build records its source revision", () => {
	const builds = dockerWorkflow.match(/uses: docker\/build-push-action@/g) || []
	const labels = dockerWorkflow.match(/labels: org\.opencontainers\.image\.revision=\$\{\{ github\.sha \}\}/g) || []
	assert.ok(builds.length >= 3)
	assert.equal(labels.length, builds.length)
})

test("jobs after a skipped test caller state explicit status checks", () => {
	for (const job of ["build", "build-cloud-shell", "manifest"]) {
		assert.match(
			jobBlock(dockerWorkflow, job),
			/^    if: \$\{\{ github\.event_name != 'pull_request' && !cancelled\(\) && needs\.changes\.result == 'success' && needs\.changes\.outputs\.is_pr != 'true' && /m,
			`${job} must not rely on implicit success()`,
		)
	}
})

test("manifests publish per target from verified digests behind a stale re-run guard", () => {
	const job = jobBlock(dockerWorkflow, "manifest")
	assert.match(job, /needs: \[changes, build\]/)
	assert.match(job, /strategy:\s+fail-fast: false\s+matrix:/)
	assert.match(job, /sparse-checkout: scripts\/ci/)

	const verify = stepBlock(job, "Verify per-arch images for this revision")
	assert.match(verify, /node scripts\/ci\/image-revision\.js verify "\$\{IMG\}:\$\{BASE\}-\$\{arch\}" "\$\{GITHUB_SHA\}"/)

	const create = stepBlock(job, "Create multi-arch manifest")
	assert.match(create, /AMD64_DIGEST: \$\{\{ steps\.verify\.outputs\.amd64 \}\}/)
	assert.match(create, /SOURCES=\("\$\{IMG\}@\$\{AMD64_DIGEST\}"\)/)
	// guard 는 태그가 추적하는 브랜치(:nightly→main, :dev→dev)의 끝을 확인해 force-push rollback 을 stale
	// re-run 과 구분한다(4번째 인자). 실행 ref(EFFECTIVE_REF)가 아니다: 다른 브랜치의 dispatch 도 :dev 로 간다.
	const finalTags = stepBlock(job, "Compute final tags")
	assert.match(finalTags, /primary="\$\{IMG\}:nightly";[^\n]*branch_tag=true; tracked_ref="refs\/heads\/main"\n/)
	assert.match(finalTags, /primary="\$\{IMG\}:dev";[^\n]*branch_tag=true; tracked_ref="refs\/heads\/dev"\n/)
	assert.match(finalTags, /branch_tag=false; tracked_ref=""\n/)
	assert.match(finalTags, /echo "tracked_ref=\$\{tracked_ref\}"/)
	assert.match(create, /TRACKED_REF: \$\{\{ steps\.tags\.outputs\.tracked_ref \}\}/)
	assert.match(
		create,
		/node scripts\/ci\/image-revision\.js guard "\$\{PRIMARY\}" "\$\{GITHUB_SHA\}" "\$\{GITHUB_REPOSITORY\}" "\$\{TRACKED_REF\}"\n/,
	)
	assert.ok(create.indexOf("image-revision.js guard") < create.indexOf("imagetools create"))
	assert.doesNotMatch(create, /imagetools create[^\n]*:\$\{BASE\}-amd64/)
	// guard exit code 는 정확히 세 갈래다: 0 발행, 3 stale 건너뜀, 그 밖(예: 인자 누락 exit 2)은 leg 실패.
	// `*) ;;` 나 추가 arm 으로 오류를 삼키면 guard 가 조용히 꺼진 채 발행한다.
	const guardCase = (skipArm) =>
		new RegExp(
			String.raw`image-revision\.js guard [^\n]*\n\s+rc=\$\?\n\s+set -e\n\s+case "\$rc" in\n\s+0\) ;;\n\s+3\) ` +
				skipArm +
				String.raw` ;;\n\s+\*\) echo "::error::stale re-run guard failed with exit \$\{rc\}"; exit "\$rc" ;;\n\s+esac\n`,
		)
	assert.match(create, guardCase("exit 0"))
	assert.match(create, /set \+e\n\s+node scripts\/ci\/image-revision\.js guard /)
	const errorArms = dockerWorkflow.match(/^\s+\*\) echo "::error::stale re-run guard failed with exit \$\{rc\}"; exit "\$rc" ;;$/gm) || []
	assert.equal(errorArms.length, 2, "both guard call sites fail on unexpected exit codes")
	assert.equal((dockerWorkflow.match(/case "\$rc" in/g) || []).length, 2)
	for (const [name, step] of [
		["verify", verify],
		["create", create],
		["final tags", finalTags],
	]) {
		assertGatingStep(step, `manifest ${name} step`)
	}
	assert.doesNotMatch(job, /^    continue-on-error:/m)

	const cloudShell = jobBlock(dockerWorkflow, "build-cloud-shell")
	const guard = stepBlock(cloudShell, "Stale re-run guard")
	assert.match(guard, /afterglow-cloud-shell:dev"\n\s+TRACKED_REF="refs\/heads\/dev"\n/)
	assert.match(guard, /afterglow-cloud-shell:nightly"\n\s+TRACKED_REF="refs\/heads\/main"\n/)
	assert.match(
		guard,
		/node scripts\/ci\/image-revision\.js guard "\$\{BRANCH_TAG\}" "\$\{GITHUB_SHA\}" "\$\{GITHUB_REPOSITORY\}" "\$\{TRACKED_REF\}"\n/,
	)
	// 모든 guard 호출은 4개 인자 형식이고 4번째는 추적 브랜치다(빠지면 image-revision.js 가 exit 2 로 leg 를 실패시킨다).
	const guardCalls = dockerWorkflow.match(/image-revision\.js guard [^\n]*/g) || []
	assert.equal(guardCalls.length, 2)
	for (const call of guardCalls) assert.match(call, / "\$\{TRACKED_REF\}"$/, call)
	assert.match(guard, guardCase("publish=false"))
	assert.match(guard, /^\s+publish=true\n\s+if \[\[ "\$\{EFFECTIVE_REF\}" != refs\/tags\/v\* \]\]; then\n/m)
	assert.match(guard, /echo "publish=\$\{publish\}" >> "\$GITHUB_OUTPUT"/)
	assertGatingStep(guard, "Cloud Shell stale re-run guard")
	assert.doesNotMatch(cloudShell, /^    continue-on-error:/m)
	assert.match(stepBlock(cloudShell, "Build and push Cloud Shell"), /if: steps\.guard\.outputs\.publish == 'true'/)
	assert.ok(cloudShell.indexOf("Stale re-run guard") < cloudShell.indexOf("Build and push Cloud Shell"))
})

test("push runs are never cancelled by a concurrency group", () => {
	for (const [name, workflow] of [["docker-build.yml", dockerWorkflow], ["test.yml", testWorkflow]]) {
		for (const match of workflow.matchAll(/^\s*cancel-in-progress:\s*(.+)$/gm)) {
			const value = match[1].trim()
			assert.ok(
				value === "false" || (value.startsWith("${{") && value.includes("github.event_name == 'pull_request'")),
				`${name}: cancel-in-progress must not apply to push runs (${value})`,
			)
		}
	}
})

// ─── CI 규정 10번: public 저장소의 pull_request 코드를 self-hosted runner 에서 실행하지 않는다 ───────────
/** top-level `jobs:` 아래의 job 이름 → 블록. `on:` 아래의 2칸 키(push, pull_request 등)는 job 이 아니다. */
function workflowJobs(workflow) {
	const lines = workflow.split("\n")
	const start = lines.findIndex((line) => /^jobs:\s*$/.test(line))
	assert.ok(start >= 0, "workflow must have a top-level jobs: key")
	const jobs = new Map()
	let name = null
	let body = []
	for (const line of lines.slice(start + 1)) {
		if (/^[^\s#]/.test(line)) break
		const key = /^  ([A-Za-z0-9_-]+):\s*(#.*)?$/.exec(line)
		if (key) {
			if (name) jobs.set(name, body.join("\n"))
			name = key[1]
			body = [line]
		} else if (name) {
			body.push(line)
		}
	}
	if (name) jobs.set(name, body.join("\n"))
	return jobs
}

/** job 의 한 줄 `runs-on:` 값(따옴표·주석 제거). 없으면 null, block list/mapping 이면 "". */
function runsOnValue(job) {
	const match = /^    runs-on:(.*)$/m.exec(job)
	if (!match) return null
	return match[1].replace(/\s+#.*$/, "").trim().replace(/^(['"])(.*)\1$/, "$2")
}

// GitHub-hosted 로 인정하는 것은 한 줄 리터럴 label 뿐이다. expression(`${{ matrix.runner }}`), 목록, group/labels
// mapping, 사용자 label 은 self-hosted 일 수 있는 것으로 본다(fail-closed).
const HOSTED_LABEL = /^(ubuntu|windows|macos)-[A-Za-z0-9.]+$/
const PR_EXCLUSION = "github.event_name != 'pull_request'"

/** GitHub expression 의 최상위 `&&` 항. 최상위 `||` 가 있으면 null(어떤 항도 전체를 제한하지 못한다). */
function topLevelConjuncts(expression) {
	const parts = []
	let depth = 0
	let quoted = false
	let current = ""
	for (let i = 0; i < expression.length; i++) {
		const char = expression[i]
		if (quoted) {
			current += char
			if (char === "'") {
				if (expression[i + 1] === "'") {
					current += "'"
					i++
				} else {
					quoted = false
				}
			}
			continue
		}
		if (char === "'") quoted = true
		else if (char === "(") depth++
		else if (char === ")") depth--
		else if (depth === 0 && expression.startsWith("||", i)) return null
		else if (depth === 0 && expression.startsWith("&&", i)) {
			parts.push(current.trim())
			current = ""
			i++
			continue
		}
		current += char
	}
	parts.push(current.trim())
	return parts
}

/** job `if:` 의 최상위 conjunct. `if:` 가 없거나 최상위 `||` 가 있으면 []. */
function jobConjuncts(job) {
	const match = /^    if:(.*)$/m.exec(job)
	if (!match) return []
	let expression = match[1].trim()
	const wrapped = /^\$\{\{([\s\S]*)\}\}$/.exec(expression)
	if (wrapped) expression = wrapped[1].trim()
	return topLevelConjuncts(expression) ?? []
}

/** job 의 `if:` 가 최상위 conjunct 로 `github.event_name != 'pull_request'` 를 갖는지. */
function excludesPullRequests(job) {
	return jobConjuncts(job).includes(PR_EXCLUSION)
}

// PR 코드가 실행되거나 PR head 를 checkout 할 수 있는 trigger. pull_request_target 은 아래에서 따로 금지한다.
// issue_comment·workflow_run 은 기본 브랜치의 workflow 로 실행되지만 job 이 PR head(head_sha 등)를 checkout 할 수 있고,
// 이 이벤트에서 `github.event_name != 'pull_request'` 는 항상 참이므로 PR 을 제외하지 못한다.
const PR_REACHABLE_EVENTS = new Set([
	"pull_request",
	"pull_request_review",
	"pull_request_review_comment",
	"issue_comment",
	"workflow_run",
	"merge_group",
])

/**
 * `on:` 의 trigger 이름. scalar(`on: push`), inline list, block list(`  - push`), mapping(`  push:`) 형식을 파싱한다.
 * 파서가 모르는 형식(flow mapping `on: {issue_comment: ...}`, 따옴표 key `  "workflow_run":`)에서도 PR 도달 trigger 를
 * 놓치지 않도록, 주석을 뺀 `on:` 블록에 PR 도달 이벤트 이름이 단어로 나오면 더한다(fail-closed).
 * `\bpull_request\b` 는 `pull_request_review`·`pull_request_target` 안에서 매치하지 않는다.
 */
function workflowTriggers(workflow) {
	const lines = workflow.split("\n")
	const start = lines.findIndex((line) => /^on:/.test(line))
	assert.ok(start >= 0, "workflow must declare on:")
	const block = [lines[start].slice(3)]
	for (const line of lines.slice(start + 1)) {
		if (/^[^\s#]/.test(line)) break
		block.push(line)
	}
	const uncommented = block.map((line) => line.replace(/(^|\s)#.*$/, "")).join("\n")

	const triggers = []
	const inline = block[0].replace(/\s+#.*$/, "").trim()
	if (inline) {
		triggers.push(
			...inline
				.replace(/^\[|\]$/g, "")
				.split(",")
				.map((name) => name.trim().replace(/^(['"])(.*)\1$/, "$2"))
				.filter(Boolean),
		)
	} else {
		for (const line of block.slice(1)) {
			const key = /^  (?:- )?([A-Za-z_]+)(?=\s*(?::|#|$))/.exec(line)
			if (key) triggers.push(key[1])
		}
	}
	for (const event of PR_REACHABLE_EVENTS) {
		if (!triggers.includes(event) && new RegExp(`\\b${event}\\b`).test(uncommented)) triggers.push(event)
	}
	return triggers
}

/**
 * job 이 workflow 의 PR 도달 trigger 에서 모두 제외되는지.
 * - allow-list: 최상위 conjunct `github.event_name == '<PR 도달이 아닌 이벤트>'`(push, workflow_dispatch 등)는 모두 제외한다.
 * - deny-list: `github.event_name != 'pull_request'` 는 PR 도달 trigger 가 pull_request 뿐일 때만 충분하다.
 */
function excludedFromPrEvents(job, prEvents) {
	const parts = jobConjuncts(job)
	const allowListed = parts.some((part) => {
		const match = /^github\.event_name == '([a-z_]+)'$/.exec(part)
		return match !== null && !PR_REACHABLE_EVENTS.has(match[1]) && match[1] !== "pull_request_target"
	})
	if (allowListed) return true
	return parts.includes(PR_EXCLUSION) && prEvents.every((event) => event === "pull_request")
}

/**
 * CI 규정 10번 검사(순수 함수). workflows 는 [파일 이름, 내용] 목록이다.
 * - non-hosted runner(한 줄 hosted label 이 아닌 모든 것)를 쓰는 job 은 PR 도달 trigger 에서 제외돼야 한다. trigger 가
 *   아직 없어도 allow-list 나 `!= 'pull_request'` conjunct 를 요구한다(나중에 pull_request 가 추가돼도 막히도록).
 * - PR 에서 도달하는 job 은 hosted label 이어야 하고, PR 에서 도달하는 reusable caller 의 호출 대상은 모든 job 이 ubuntu-* 이다.
 */
function selfHostedPrViolations(workflows) {
	const byName = new Map(workflows)
	const violations = []
	const nonHosted = []
	const prReachableCallees = new Set()
	for (const [name, text] of workflows) {
		// pull_request_target 은 base 저장소 권한과 secrets 로 실행되고 `!= 'pull_request'` 로도 제외되지 않는다.
		if (/\bpull_request_target\b/.test(text)) violations.push(`${name} must not use pull_request_target`)
		const prEvents = workflowTriggers(text).filter((event) => PR_REACHABLE_EVENTS.has(event))
		const jobs = workflowJobs(text)
		if (jobs.size === 0) violations.push(`${name} must have jobs`)
		for (const [job, block] of jobs) {
			const label = `${name} ${job}`
			const prReachable = prEvents.length > 0 && !excludedFromPrEvents(block, prEvents)
			const runsOn = runsOnValue(block)
			if (runsOn === null) {
				// reusable workflow caller: PR 에서 도달하면 호출 대상의 모든 잡을 아래에서 확인한다.
				if (!/^    uses:/m.test(block)) violations.push(`${label} must declare runs-on or call a reusable workflow`)
				if (prReachable) {
					const callee = /^    uses: \.\/\.github\/workflows\/([A-Za-z0-9_.-]+)\s*$/m.exec(block)
					if (callee) prReachableCallees.add(callee[1])
					else violations.push(`${label} is reachable from PR events and must call a local reusable workflow`)
				}
				continue
			}
			if (!HOSTED_LABEL.test(runsOn)) {
				nonHosted.push(label)
				const guarded = excludedFromPrEvents(block, prEvents.length > 0 ? prEvents : ["pull_request"])
				if (!guarded) {
					violations.push(
						`${label} runs on ${runsOn || "a block-form runner"}; its if needs a top-level allow-list conjunct ` +
							`(github.event_name == 'push' etc.) or ${PR_EXCLUSION} when pull_request is its only PR trigger ` +
							`(PR triggers: ${prEvents.join(", ") || "none"})`,
					)
				}
			}
			// hosted label 이 아닌 job 은 위 guard 로 PR 도달에서 제외되므로, PR 에서 도달하는 job 은 모두 hosted 이다.
		}
	}
	for (const callee of prReachableCallees) {
		if (!byName.has(callee)) {
			violations.push(`${callee} must exist`)
			continue
		}
		for (const [job, block] of workflowJobs(byName.get(callee))) {
			if (!/^ubuntu-/.test(runsOnValue(block) ?? "")) violations.push(`${callee} ${job} runs PR code and must use ubuntu-*`)
		}
	}
	return { violations, nonHosted, prReachableCallees }
}

test("the PR-exclusion parser only accepts a real top-level conjunct", () => {
	assert.deepEqual(topLevelConjuncts("a && b"), ["a", "b"])
	assert.equal(topLevelConjuncts(`${PR_EXCLUSION} && b || c`), null)
	assert.deepEqual(topLevelConjuncts(`(${PR_EXCLUSION} || x) && c`), [`(${PR_EXCLUSION} || x)`, "c"])
	assert.deepEqual(topLevelConjuncts("'a && b' && c"), ["'a && b'", "c"])
	assert.deepEqual(topLevelConjuncts("'it''s || x' && c"), ["'it''s || x'", "c"])
	assert.equal(excludesPullRequests(`    if: \${{ ${PR_EXCLUSION} && !cancelled() }}`), true)
	assert.equal(excludesPullRequests(`    if: ${PR_EXCLUSION}`), true)
	assert.equal(excludesPullRequests(`    if: \${{ ${PR_EXCLUSION} || always() }}`), false)
	assert.equal(excludesPullRequests(`    if: \${{ !(${PR_EXCLUSION}) }}`), false)
	assert.equal(excludesPullRequests("    if: needs.changes.outputs.is_pr != 'true'"), false)
	assert.equal(excludesPullRequests("    runs-on: ubuntu-latest"), false)
	assert.equal(runsOnValue("    runs-on: ubuntu-latest"), "ubuntu-latest")
	assert.equal(runsOnValue("    runs-on: 'ubuntu-24.04'  # pinned"), "ubuntu-24.04")
	assert.equal(HOSTED_LABEL.test(runsOnValue("    runs-on: [self-hosted, linux, x64]")), false)
	assert.equal(HOSTED_LABEL.test(runsOnValue("    runs-on: ${{ matrix.runner }}")), false)
	assert.equal(HOSTED_LABEL.test(runsOnValue("    runs-on:\n      group: build")), false)
})

test("workflow triggers parse in scalar, inline list, block list and mapping form", () => {
	assert.deepEqual(workflowTriggers("on: issue_comment\njobs:\n"), ["issue_comment"])
	assert.deepEqual(workflowTriggers("on: [push, pull_request]\njobs:\n"), ["push", "pull_request"])
	assert.deepEqual(workflowTriggers("on: ['push', \"workflow_run\"]  # quoted\njobs:\n"), ["push", "workflow_run"])
	assert.deepEqual(workflowTriggers("on:\n  - push\n  - pull_request\njobs:\n"), ["push", "pull_request"])
	assert.deepEqual(
		workflowTriggers("on:\n  # comment\n  pull_request:\n    branches: [main]\n  workflow_run:\n    workflows: [x]\n  push: {branches: [main]}\njobs:\n"),
		["pull_request", "workflow_run", "push"],
	)
	// jobs: 아래의 2칸 키는 trigger 가 아니다.
	assert.deepEqual(workflowTriggers("on:\n  push:\n    branches: [main]\njobs:\n  pull_request:\n"), ["push"])
	// 파서가 모르는 형식에서도 PR 도달 이벤트 이름은 단어 검색으로 더한다. 주석과 다른 이벤트의 접두사는 무시한다.
	assert.ok(workflowTriggers("on: {issue_comment: {types: [created]}}\njobs:\n").includes("issue_comment"))
	assert.ok(workflowTriggers('on:\n  "workflow_run":\n    workflows: [x]\njobs:\n').includes("workflow_run"))
	assert.deepEqual(workflowTriggers("on:\n  push:  # not issue_comment\n  pull_request_review:\njobs:\n"), ["push", "pull_request_review"])
	assert.deepEqual(workflowTriggers("on:\n  - push\n  - workflow_dispatch\njobs:\n"), ["push", "workflow_dispatch"])
})

test("the rule 10 check treats issue_comment and workflow_run as PR-reachable", () => {
	const workflow = (on, job) => `name: x\non:\n${on}\njobs:\n  j:\n${job}\n    steps:\n      - run: true\n`
	const selfHosted = (condition) => `${condition ? `    if: ${condition}\n` : ""}    runs-on: [self-hosted, linux, x64]`
	const check = (text) => selfHostedPrViolations([["w.yml", text]]).violations
	// deny-list 는 pull_request 만 제외한다. issue_comment/workflow_run/리뷰 이벤트에서는 항상 참이다.
	for (const event of ["issue_comment", "workflow_run", "pull_request_review", "pull_request_review_comment", "merge_group"]) {
		assert.equal(check(workflow(`  ${event}:`, selfHosted(PR_EXCLUSION))).length, 1, `${event} with the deny-list only`)
		assert.equal(check(workflow(`  push:\n  ${event}:`, selfHosted(PR_EXCLUSION))).length, 1, `push + ${event} with the deny-list only`)
		// allow-list 는 모든 PR 도달 이벤트를 제외한다.
		assert.deepEqual(check(workflow(`  push:\n  ${event}:`, selfHosted("github.event_name == 'push'"))), [], `${event} + allow-list`)
		// 제외되지 않은 hosted job 은 허용되고, reusable caller 는 호출 대상까지 확인한다.
		assert.deepEqual(check(workflow(`  ${event}:`, "    runs-on: ubuntu-latest")), [], `${event} on a hosted runner`)
	}
	// 파서가 모르는 형식(flow mapping, 따옴표 key)도 PR 도달 trigger 로 본다.
	assert.equal(check(`name: x\non: {issue_comment: {types: [created]}}\njobs:\n  j:\n${selfHosted(PR_EXCLUSION)}\n    steps:\n      - run: true\n`).length, 1)
	assert.equal(check(workflow('  "workflow_run":\n    workflows: [x]', selfHosted(PR_EXCLUSION))).length, 1)
	// allow-list 가 PR 도달 이벤트면 제외가 아니다.
	assert.equal(check(workflow("  issue_comment:", selfHosted("github.event_name == 'issue_comment'"))).length, 1)
	assert.equal(check(workflow("  pull_request:", selfHosted("github.event_name == 'pull_request_target'"))).length, 2)
	// pull_request 만 있으면 deny-list 로 충분하다. trigger 가 없어도 non-hosted job 에는 guard 를 요구한다.
	assert.deepEqual(check(workflow("  push:\n  pull_request:", selfHosted(PR_EXCLUSION))), [])
	assert.deepEqual(check(workflow("  schedule:\n    - cron: '0 0 * * *'", selfHosted(PR_EXCLUSION))), [])
	assert.equal(check(workflow("  schedule:\n    - cron: '0 0 * * *'", selfHosted(null))).length, 1)
	assert.equal(check(workflow("  push:\n  pull_request:", selfHosted(`${PR_EXCLUSION} || always()`))).length, 1)
	// PR 에서 도달하는 reusable caller 의 호출 대상은 모든 job 이 ubuntu-* 여야 한다.
	const caller = workflow("  issue_comment:", "    uses: ./.github/workflows/callee.yml")
	const callee = (runsOn) => `name: c\non:\n  workflow_call:\njobs:\n  k:\n    runs-on: ${runsOn}\n    steps:\n      - run: true\n`
	assert.deepEqual(selfHostedPrViolations([["w.yml", caller], ["callee.yml", callee("ubuntu-latest")]]).violations, [])
	assert.equal(
		selfHostedPrViolations([["w.yml", caller], ["callee.yml", callee("[self-hosted, linux, x64]")]]).violations.length,
		2,
		"the callee's self-hosted job is reachable and unguarded",
	)
})

test("pull_request code never runs on a self-hosted runner", () => {
	const { violations, nonHosted, prReachableCallees } = selfHostedPrViolations(allWorkflows)
	assert.deepEqual(violations, [])
	// 분류기 sanity: self-hosted build matrix(runs-on: ${{ matrix.runner }})는 non-hosted 로 잡힌다.
	assert.ok(nonHosted.includes("docker-build.yml build"), nonHosted.join(", "))
	const dockerJobs = workflowJobs(dockerWorkflow)
	assert.equal(dockerJobs.has("push"), false, "on: keys are not jobs")
	// PR 이 publishing 잡(packages: write)을 예약하지 못한다. step 이 계산하는 is_pr 는 보조 확인일 뿐이다.
	for (const job of ["build", "build-cloud-shell", "manifest"]) {
		assert.equal(excludesPullRequests(dockerJobs.get(job)), true, `${job} must exclude pull_request by event name`)
	}
	// PR 에서 실행되는 docker-build 잡과 test-pr 의 호출 대상은 GitHub-hosted ubuntu 이다.
	for (const job of ["pr-dedup", "changes"]) {
		assert.equal(excludesPullRequests(dockerJobs.get(job)), false, `${job} runs on pull_request`)
		assert.match(runsOnValue(dockerJobs.get(job)), /^ubuntu-/, `${job} runs PR code`)
	}
	assert.ok(prReachableCallees.has("test.yml"), [...prReachableCallees].join(", "))
	for (const [job, block] of workflowJobs(testWorkflow)) {
		assert.match(runsOnValue(block) ?? "", /^ubuntu-/, `test.yml ${job} must use a GitHub-hosted ubuntu label`)
	}
})
