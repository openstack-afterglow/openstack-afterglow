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

test("service containers use the dev compose test-profile health timing", () => {
	const intervals = Array.from(testWorkflow.matchAll(/--health-interval[= ](\S+)/g), (m) => m[1])
	const timeouts = Array.from(testWorkflow.matchAll(/--health-timeout[= ](\S+)/g), (m) => m[1])
	const retries = Array.from(testWorkflow.matchAll(/--health-retries[= ](\S+)/g), (m) => m[1])
	assert.equal(intervals.length, 4, "mariadb, postgres, functional redis and live redis")
	assert.deepEqual([...new Set(intervals)], ["2s"])
	assert.deepEqual([...new Set(timeouts)], ["5s"])
	assert.deepEqual([...new Set(retries)], ["20"])

	const compose = fs.readFileSync(path.join(rootDir, "docker-compose.dev.yml"), "utf8")
	for (const service of ["mariadb", "postgres", "test-redis"]) {
		const start = compose.indexOf(`\n  ${service}:\n`)
		assert.ok(start >= 0, `compose ${service} must exist`)
		const block = compose.slice(start, start + 1200)
		assert.match(block, /interval: 2s\s+timeout: 5s\s+retries: 20/, `compose ${service} health timing`)
	}
})

test("PR dedup skips only same-repo dev PRs whose merge tree equals the head tree", () => {
	const job = jobBlock(dockerWorkflow, "pr-dedup")
	assert.match(job, /^    if: github\.event_name == 'pull_request'\s*$/m)
	assert.match(job, /runs-on: ubuntu-latest/)
	assert.match(job, /^    permissions:\n      contents: read\n    outputs:\n      skip: \$\{\{ steps\.dedup\.outputs\.skip \}\}\n/m)
	// 판단 step 은 항상 성공하므로 job-level continue-on-error 는 인프라 실패만 가린다. 실패는 red 로 드러낸다.
	assert.doesNotMatch(job, /^    continue-on-error:/m, "pr-dedup must not hide its own failure")

	// checkout 실패는 다음 step 의 fallback 이 skip=false 로 처리한다.
	const checkout = stepBlock(job, "Checkout PR merge commit")
	assert.match(checkout, /continue-on-error: true/)
	assert.match(checkout, /persist-credentials: false/)

	const dedup = stepBlock(job, "Compare merge tree with head tree")
	assert.match(dedup, /id: dedup/)
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
	assert.ok(fs.existsSync(path.join(rootDir, "scripts", "ci", "pr-dedup.js")))

	// push/dispatch caller 에는 skipped 조상이 없어야 한다(암묵적 success() 가 내부 잡을 건너뛰지 않도록).
	const testJob = jobBlock(dockerWorkflow, "test")
	assert.doesNotMatch(testJob, /^    needs:/m)
	assert.match(testJob, /^    if: github\.event_name != 'pull_request'\s*$/m)
	assert.match(testJob, /uses: \.\/\.github\/workflows\/test\.yml/)

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
	assert.match(detect, /"diff", "--name-only", before, head/)
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
			/^    if: \$\{\{ !cancelled\(\) && needs\.changes\.result == 'success' && needs\.changes\.outputs\.is_pr != 'true' && /m,
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
