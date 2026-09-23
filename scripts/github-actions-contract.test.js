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

test("test jobs start at t=0: no job waits on version-check", () => {
	assert.match(testWorkflow, /^  version-check:\s*$/m)
	for (const job of ["test-backend", "test-cloud-shell", "test-contract", "test-functional", "test-frontend", "detect-live"]) {
		const block = jobBlock(testWorkflow, job)
		assert.doesNotMatch(block, /^\s+needs:.*version-check/m, `${job} must not need version-check`)
		assert.doesNotMatch(block, /^\s+- version-check\s*$/m, `${job} must not list version-check`)
	}
	// 빌드 게이팅은 docker-build.yml changes 가 reusable test workflow 전체에 걸어 유지한다.
	const changes = jobBlock(dockerWorkflow, "changes")
	assert.match(changes, /^    needs: \[test, test-pr\]\s*$/m)
	assert.match(
		changes,
		/^    if: \$\{\{ !cancelled\(\) && \(needs\.test\.result == 'success' \|\| needs\.test-pr\.result == 'success'\) \}\}\s*$/m,
	)
})

test("functional tests always run and live tests still wait on every test layer", () => {
	assert.doesNotMatch(jobBlock(testWorkflow, "test-functional"), /^    if:/m)
	assert.match(
		jobBlock(testWorkflow, "test-live"),
		/needs: \[test-backend, test-contract, test-functional, test-frontend, detect-live\]/,
	)
})

test("frontend runs as a verified 2-way vitest shard matrix", () => {
	const job = jobBlock(testWorkflow, "test-frontend")
	assert.match(job, /name: Frontend \(unit tests \$\{\{ matrix\.shard \}\}\/2\)/)
	assert.match(job, /strategy:\s+fail-fast: false\s+matrix:\s+shard: \[1, 2\]/)

	// 래퍼(npm run/npm test) 뒤의 `-- --shard` 는 인자가 전달되지 않으므로 vitest 를 직접 호출한다.
	const run = stepBlock(job, "Test (vitest shard")
	assert.match(run, /\.\/node_modules\/\.bin\/vitest run/)
	assert.match(run, /--shard=\$\{\{ matrix\.shard \}\}\/2/)
	assert.match(run, /--reporter=json/)
	assert.match(run, /--reporter=github-actions/)
	const report = /--outputFile\.json=(\S+)/.exec(run)
	assert.ok(report, "vitest must write a JSON report")
	assert.doesNotMatch(job, /npm run test:unit:frontend|run: npm test/)

	const verify = stepBlock(job, "Verify shard file count")
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
	assert.match(job, /permissions:\s+contents: read\s+outputs:/)
	assert.match(job, /HEAD_REPO: \$\{\{ github\.event\.pull_request\.head\.repo\.full_name \}\}/)
	assert.match(job, /BASE_REPO: \$\{\{ github\.repository \}\}/)
	assert.match(job, /HEAD_REF: \$\{\{ github\.head_ref \}\}/)
	assert.match(job, /HEAD_SHA: \$\{\{ github\.event\.pull_request\.head\.sha \}\}/)

	const script = job.slice(job.indexOf("run: |"))
	// 공격자가 정하는 브랜치 이름은 env 로만 전달한다(쉘 보간 금지).
	assert.doesNotMatch(script, /\$\{\{/)
	assert.match(script, /"\$HEAD_REPO" != "\$BASE_REPO"/)
	assert.match(script, /"\$HEAD_REF" != "dev"/)
	assert.match(script, /git fetch --no-tags --depth=1 origin "\$HEAD_SHA"/)
	assert.match(script, /git rev-parse 'HEAD\^\{tree\}'/)
	assert.match(script, /git rev-parse "\$\{HEAD_SHA\}\^\{tree\}"/)
	assert.match(script, /"\$merge_tree" = "\$head_tree"/)
	assert.match(script, /^\s+skip=false\s*$/m)
	assert.equal(script.match(/>> "\$GITHUB_OUTPUT"/g).length, 1, "skip is written exactly once")

	assert.match(job, /^    continue-on-error: true\s*$/m)

	// push/dispatch caller 에는 skipped 조상이 없어야 한다(암묵적 success() 가 내부 잡을 건너뛰지 않도록).
	const testJob = jobBlock(dockerWorkflow, "test")
	assert.doesNotMatch(testJob, /^    needs:/m)
	assert.match(testJob, /^    if: github\.event_name != 'pull_request'\s*$/m)
	assert.match(testJob, /uses: \.\/\.github\/workflows\/test\.yml/)

	const prTestJob = jobBlock(dockerWorkflow, "test-pr")
	assert.match(prTestJob, /^    needs: pr-dedup\s*$/m)
	assert.match(prTestJob, /^    if: \$\{\{ !cancelled\(\) && needs\.pr-dedup\.outputs\.skip != 'true' \}\}\s*$/m)
	assert.match(prTestJob, /uses: \.\/\.github\/workflows\/test\.yml/)
	assert.match(prTestJob, /run_live_openstack: false/)
})

test("image target detection diffs event.before on push, never only the tip commit", () => {
	const job = jobBlock(dockerWorkflow, "changes")
	assert.doesNotMatch(dockerWorkflow, /git diff --name-only HEAD\^1 HEAD/)
	assert.match(job, /EVENT_BEFORE: \$\{\{ github\.event\.before \}\}/)
	assert.match(job, /EVENT_FORCED: \$\{\{ github\.event\.forced \}\}/)
	assert.match(job, /run: node scripts\/ci\/detect-build-targets\.js/)
	for (const output of ["targets", "standard_targets", "effective_ref", "cloud_shell", "is_pr"]) {
		assert.match(job, new RegExp(`^      ${output}: \\$\\{\\{ steps\\.`, "m"), `changes output ${output}`)
	}

	// 레지스트리 자격 증명과 compare 토큰은 push 에서만 사용한다(PR 코드가 이 job 을 실행한다).
	const login = stepBlock(job, "Log in to registry (push only")
	assert.match(login, /if: github\.event_name == 'push'/)
	assert.match(job, /GH_TOKEN: \$\{\{ github\.event_name == 'push' && github\.token \|\| '' \}\}/)
	assert.match(job, /packages: read/)

	const detect = fs.readFileSync(path.join(rootDir, "scripts", "ci", "detect-build-targets.js"), "utf8")
	assert.match(detect, /env\.EVENT_BEFORE/)
	assert.match(detect, /"fetch", "--no-tags", "--depth=1", "origin", before/)
	assert.match(detect, /"diff", "--name-only", before, head/)
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
	assert.match(create, /node scripts\/ci\/image-revision\.js guard "\$\{PRIMARY\}" "\$\{GITHUB_SHA\}" "\$\{GITHUB_REPOSITORY\}"/)
	assert.ok(create.indexOf("image-revision.js guard") < create.indexOf("imagetools create"))
	assert.doesNotMatch(create, /imagetools create[^\n]*:\$\{BASE\}-amd64/)
	assert.match(create, /3\) exit 0 ;;/)

	const cloudShell = jobBlock(dockerWorkflow, "build-cloud-shell")
	const guard = stepBlock(cloudShell, "Stale re-run guard")
	assert.match(guard, /node scripts\/ci\/image-revision\.js guard "\$\{BRANCH_TAG\}" "\$\{GITHUB_SHA\}" "\$\{GITHUB_REPOSITORY\}"/)
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
