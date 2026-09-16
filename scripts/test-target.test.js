const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")
const { spawn } = require("node:child_process")

const rootDir = path.resolve(__dirname, "..")
const scriptPath = path.join(rootDir, "scripts", "test-target.js")
const fakeRunnerSource = `#!/usr/bin/env node
const fs = require("node:fs")
const path = require("node:path")

const logFile = process.env.TEST_TARGET_LOG_FILE
const delayMs = Number(process.env.TEST_TARGET_DELAY_MS || "150")
const failStep = process.env.TEST_TARGET_FAIL_STEP || ""
const failCode = Number(process.env.TEST_TARGET_FAIL_CODE || "7")
const startBarrierCount = Number(process.env.TEST_TARGET_START_BARRIER_COUNT || "0")
const startBarrierTimeoutMs = Number(process.env.TEST_TARGET_START_BARRIER_TIMEOUT_MS || "2000")

function append(event) {
	fs.appendFileSync(logFile, JSON.stringify(event) + "\\n")
}

function getStepLabel() {
	const lane = path.basename(process.cwd())
	const args = process.argv.slice(2)

	if (lane === "backend") {
		const pytestIndex = args.indexOf("pytest")
		const selector = pytestIndex === -1 ? "" : args.slice(pytestIndex + 1).find((arg) => !arg.startsWith("-")) || ""
		if (selector === "tests/test_auth_endpoints.py") return "auth [backend]"
		if (selector === "tests/test_afterglow_conf_config.py") return "config [backend]"
	}

	if (lane === "frontend") {
		const selector = args.find((arg) => arg.startsWith("src/")) || ""
		if (selector === "src/lib/stores/__tests__/auth.test.ts") return "auth [frontend]"
		if (selector === "src/lib/config/site.test.ts") return "config [frontend]"
	}

	return lane + ":" + args.join(" ")
}

function finishAfterDelay() {
	setTimeout(() => {
		append({ type: "end", step, at: Date.now(), pid: process.pid })
		process.exit(step === failStep ? failCode : 0)
	}, delayMs)
}

function waitForStartBarrier() {
	if (startBarrierCount === 0) {
		finishAfterDelay()
		return
	}

	const deadline = Date.now() + startBarrierTimeoutMs
	const check = () => {
		const starts = fs.existsSync(logFile)
			? (fs.readFileSync(logFile, "utf8").match(/"type":"start"/g) || []).length
			: 0
		if (starts >= startBarrierCount || Date.now() >= deadline) {
			finishAfterDelay()
			return
		}
		setTimeout(check, 5)
	}
	check()
}

const step = getStepLabel()
append({ type: "start", step, at: Date.now(), pid: process.pid })
waitForStartBarrier()
`

function makeTempDir() {
	return fs.mkdtempSync(path.join(os.tmpdir(), "test-target-"))
}

function writeExecutable(filePath, source) {
	fs.writeFileSync(filePath, source, { mode: 0o755 })
}

function parseEvents(logFile) {
	if (!fs.existsSync(logFile)) {
		return []
	}

	return fs
		.readFileSync(logFile, "utf8")
		.trim()
		.split("\n")
		.filter(Boolean)
		.map((line) => JSON.parse(line))
}

function buildIntervals(events) {
	const intervals = new Map()

	for (const event of events) {
		const current = intervals.get(event.step) || {}
		if (event.type === "start") {
			current.start = event.at
		} else if (event.type === "end") {
			current.end = event.at
		}
		intervals.set(event.step, current)
	}

	for (const [step, interval] of intervals) {
		assert.equal(typeof interval.start, "number", `Missing start event for ${step}`)
		assert.equal(typeof interval.end, "number", `Missing end event for ${step}`)
	}

	return intervals
}

function maxConcurrency(intervals) {
	const points = []
	for (const interval of intervals.values()) {
		points.push({ at: interval.start, delta: 1, kind: "start" })
		points.push({ at: interval.end, delta: -1, kind: "end" })
	}

	points.sort((left, right) => {
		if (left.at !== right.at) return left.at - right.at
		if (left.kind === right.kind) return 0
		return left.kind === "end" ? -1 : 1
	})

	let active = 0
	let peak = 0
	for (const point of points) {
		active += point.delta
		peak = Math.max(peak, active)
	}
	return peak
}

function overlaps(left, right) {
	return left.start < right.end && right.start < left.end
}

async function runCli(args, options = {}) {
	const tempDir = makeTempDir()
	const binDir = path.join(tempDir, "bin")
	const logFile = path.join(tempDir, "events.log")
	fs.mkdirSync(binDir, { recursive: true })
	writeExecutable(path.join(binDir, "uv"), fakeRunnerSource)
	writeExecutable(path.join(binDir, "npm"), fakeRunnerSource)

	const env = {
		...process.env,
		PATH: `${binDir}${path.delimiter}${process.env.PATH || ""}`,
		TEST_TARGET_LOG_FILE: logFile,
		TEST_TARGET_DELAY_MS: String(options.delayMs || 150),
		...(options.startBarrierCount
			? { TEST_TARGET_START_BARRIER_COUNT: String(options.startBarrierCount) }
			: {})
	}
	if (options.failStep) {
		env.TEST_TARGET_FAIL_STEP = options.failStep
		env.TEST_TARGET_FAIL_CODE = String(options.failCode || 7)
	}

	const result = await new Promise((resolve, reject) => {
		const child = spawn(process.execPath, [scriptPath, ...args], {
			cwd: rootDir,
			env,
			stdio: ["ignore", "pipe", "pipe"]
		})
		let stdout = ""
		let stderr = ""
		child.stdout.on("data", (chunk) => {
			stdout += chunk
		})
		child.stderr.on("data", (chunk) => {
			stderr += chunk
		})
		child.on("error", reject)
		child.on("close", (code, signal) => {
			resolve({ code, signal, stdout, stderr })
		})
	})

	result.events = parseEvents(logFile)
	result.tempDir = tempDir
	return result
}

function cleanupRun(result) {
	fs.rmSync(result.tempDir, { recursive: true, force: true })
}

test("default mode keeps the original fully serial step order", async () => {
	const result = await runCli(["auth", "config"])
	try {
		assert.equal(result.signal, null)
		assert.equal(result.code, 0, result.stderr || result.stdout)
		assert.deepEqual(
			result.events.map((event) => `${event.type}:${event.step}`),
			[
				"start:auth [backend]",
				"end:auth [backend]",
				"start:auth [frontend]",
				"end:auth [frontend]",
				"start:config [backend]",
				"end:config [backend]",
				"start:config [frontend]",
				"end:config [frontend]"
			]
		)
		assert.equal(maxConcurrency(buildIntervals(result.events)), 1)
	} finally {
		cleanupRun(result)
	}
})

test("--parallel runs exactly two lanes instead of starting every step at once", async () => {
	const result = await runCli(["--parallel", "auth", "config"], { startBarrierCount: 2 })
	try {
		assert.equal(result.signal, null)
		assert.equal(result.code, 0, result.stderr || result.stdout)
		const intervals = buildIntervals(result.events)
		assert.ok(intervals.has("auth [backend]"))
		assert.ok(intervals.has("auth [frontend]"))
		assert.equal(maxConcurrency(intervals), 2)
		assert.ok(intervals.get("auth [backend]").end <= intervals.get("config [backend]").start)
		assert.ok(intervals.get("auth [frontend]").end <= intervals.get("config [frontend]").start)
	} finally {
		cleanupRun(result)
	}
})

test("--parallel lets backend and frontend overlap while preserving in-lane order", async () => {
	const result = await runCli(["--parallel", "auth", "config"], { startBarrierCount: 2 })
	try {
		assert.equal(result.signal, null)
		assert.equal(result.code, 0, result.stderr || result.stdout)
		const intervals = buildIntervals(result.events)
		const backendSteps = [intervals.get("auth [backend]"), intervals.get("config [backend]")]
		const frontendSteps = [intervals.get("auth [frontend]"), intervals.get("config [frontend]")]
		const authBackend = intervals.get("auth [backend]")
		const configBackend = intervals.get("config [backend]")
		const authFrontend = intervals.get("auth [frontend]")
		const configFrontend = intervals.get("config [frontend]")

		assert.ok(
			backendSteps.some((backendStep) => frontendSteps.some((frontendStep) => overlaps(backendStep, frontendStep))),
			"expected at least one backend step to overlap a frontend step"
		)
		assert.ok(authBackend.end <= configBackend.start, "backend lane should stay serial")
		assert.ok(authFrontend.end <= configFrontend.start, "frontend lane should stay serial")
	} finally {
		cleanupRun(result)
	}
})

test("--parallel returns a non-zero exit code when one lane fails", async () => {
	const result = await runCli(["--parallel", "auth", "config"], {
		failStep: "config [frontend]",
		failCode: 9
	})
	try {
		assert.equal(result.signal, null)
		assert.notEqual(result.code, 0, result.stderr || result.stdout)
		assert.ok(
			result.events.some((event) => event.type === "start" && event.step === "config [frontend]"),
			"expected the failing frontend step to start"
		)
	} finally {
		cleanupRun(result)
	}
})

test("--validate checks the complete target catalog", async () => {
	const result = await runCli(["--validate"]);
	try {
		assert.equal(result.signal, null);
		assert.equal(result.code, 0, result.stderr || result.stdout);
		assert.deepEqual(result.events, []);
	} finally {
		cleanupRun(result);
	}
});

test("waygate target runs from backend root", async () => {
	const result = await runCli(["--dry-run", "waygate"])
	try {
		assert.equal(result.signal, null)
		assert.equal(result.code, 0, result.stderr || result.stdout)
		assert.match(result.stdout, /waygate \[backend\]/)
		assert.match(result.stdout, /cwd: backend/)
		assert.match(result.stdout, /cmd: uv run python -m pytest tests\/contracts\/test_waygate_proxy\.py tests\/contracts\/test_waygate_agent\.py -v/)
		assert.deepEqual(result.events, [])
	} finally {
		cleanupRun(result)
	}
})

test("service source dirs and root Docker stages cannot return and imported SDKs use immutable subdirectories", () => {
	for (const service of ["drover", "lumen", "waygate"]) {
		const serviceDir = path.join(rootDir, "services", service);
		assert.equal(
			fs.existsSync(serviceDir),
			false,
			`services/${service} directory must be removed`
		);
	}

	const dockerfileContent = fs.readFileSync(path.join(rootDir, "Dockerfile"), "utf-8");
	for (const stage of ["waygate-builder", "drover-builder", "lumen-builder"]) {
		assert.equal(
			dockerfileContent.includes(`AS ${stage}`),
			false,
			`Dockerfile must not contain stage AS ${stage}`
		);
	}

	const pyprojectContent = fs.readFileSync(path.join(rootDir, "backend", "pyproject.toml"), "utf-8");
	for (const sdk of ["waygate-sdk", "drover-sdk"]) {
		const pattern = new RegExp(`${sdk} @ git\\+https://github\\.com/openstack-afterglow/[a-z-]+\\.git@[0-9a-f]{40}#subdirectory=sdk`);
		assert.ok(
			pattern.test(pyprojectContent),
			`pyproject.toml must declare ${sdk} with immutable SHA and #subdirectory=sdk`
		);
	}
	assert.equal(pyprojectContent.includes("lumen-sdk"), false, "generic Lumen BFF must not install lumen-sdk");
})
test("package.json contains exact command contract scripts and no obsolete scripts", () => {
	const pkg = JSON.parse(fs.readFileSync(path.join(rootDir, "package.json"), "utf-8"));
	const scripts = pkg.scripts;

	assert.equal(scripts["test:unit:backend"], "cd backend && AFTERGLOW_ALLOW_INSECURE=1 uv run python -m pytest tests/ -v --ignore=tests/integration --ignore=tests/contracts -m \"not db and not contract\"");
	assert.equal(scripts["test:unit:frontend"], "cd frontend && npm test");
	assert.equal(scripts["test:unit"], "npm run test:target:js && npm run test:unit:backend && npm run test:unit:frontend");
	assert.equal(scripts["test:contract"], "node scripts/test-target.js contracts");
	assert.equal(scripts["test:functional"], "node scripts/test-db.js");
	assert.equal(scripts["test:orchestration"], "node --test scripts/test-target.test.js scripts/test-db.test.js scripts/github-actions-contract.test.js && node scripts/test-target.js --validate");
	assert.equal(scripts["test:kolla:contract"], "node --test scripts/kolla-contract.test.js");
	assert.equal(scripts["test:target:js"], "npm run test:orchestration && npm run test:kolla:contract");
	assert.equal(scripts["test:live"], "cd backend && AFTERGLOW_ALLOW_INSECURE=1 uv run python -m pytest tests/integration -v");
	assert.equal(scripts["test:all"], "npm run test:unit && npm run test:contract && npm run test:functional");
	assert.equal(scripts["test:gate"], "npm run docs:check && npm run test:all && npm run lint:backend");

	assert.equal(scripts["test:backend:app"], undefined);
	assert.equal(scripts["test:backend:integration"], undefined);
	assert.equal(scripts["test:contracts"], undefined);
	for (const key of Object.keys(scripts)) {
		assert.ok(!key.startsWith("test:integration:"), `obsolete script ${key} must be removed`);
	}
});

test("CI separates pure orchestration from uv-backed Kolla contracts", () => {
	const workflow = fs.readFileSync(path.join(rootDir, ".github", "workflows", "test.yml"), "utf-8");
	const hasRootLockfile = ["package-lock.json", "npm-shrinkwrap.json"].some((name) =>
		fs.existsSync(path.join(rootDir, name))
	);

	assert.match(workflow, /name: Test target orchestration\s+run: npm run test:orchestration/);
	assert.match(workflow, /name: Kolla contract tests\s+run: npm run test:kolla:contract/);
	assert.match(workflow, /if ! STATUS=\$\(curl/);
	assert.match(workflow, /Keystone probe transport failed or timed out/);
	const dockerWorkflow = fs.readFileSync(
		path.join(rootDir, ".github", "workflows", "docker-build.yml"),
		"utf-8",
	);
	assert.match(
		workflow,
		/workflow_call:\s+inputs:\s+run_live_openstack:[\s\S]*?type: boolean\s+default: false/,
	);
	assert.match(
		workflow,
		/detect-live:[\s\S]*?if: \$\{\{ inputs\.run_live_openstack \}\}/,
	);
	assert.match(
		dockerWorkflow,
		/workflow_dispatch:[\s\S]*?run_live_openstack:[\s\S]*?type: boolean/,
	);
	assert.match(
		dockerWorkflow,
		/with:\s+run_live_openstack: \$\{\{ github\.event_name == 'workflow_dispatch' && inputs\.run_live_openstack \}\}/,
	);
	if (!hasRootLockfile) {
		assert.doesNotMatch(workflow, /cache:\s*npm/);
		assert.doesNotMatch(workflow, /run:\s*npm ci/);
	}

	const osInterfaceFallbacks = Array.from(
		workflow.matchAll(/vars\.AFTERGLOW_OS_INTERFACE\s*\|\|\s*'([^']+)'/g),
		(m) => m[1]
	);
	assert.deepEqual(osInterfaceFallbacks, ["public", "public"]);
});

test("pull requests cannot schedule the self-hosted image build matrix", () => {
	const workflow = fs.readFileSync(path.join(rootDir, ".github", "workflows", "docker-build.yml"), "utf-8");
	const buildStart = workflow.indexOf("\n  build:");
	const manifestStart = workflow.indexOf("\n  manifest:");
	const buildJob = workflow.slice(buildStart, manifestStart);

	assert.ok(buildStart >= 0 && manifestStart > buildStart, "docker workflow build job must exist");
	assert.match(buildJob, /runs-on: \$\{\{ matrix\.runner \}\}/);
	assert.match(
		buildJob,
		/if: needs\.changes\.outputs\.is_pr != 'true' && needs\.changes\.outputs\.targets != '\[\]'/
	);
});

test("contract tests live in tests/contracts/ and do not overlap with unit collection", () => {
	const contractDir = path.join(rootDir, "backend", "tests", "contracts");
	assert.ok(fs.existsSync(contractDir), "backend/tests/contracts directory must exist");
	assert.ok(fs.existsSync(path.join(contractDir, "conftest.py")), "backend/tests/contracts/conftest.py must exist");

	const expectedContractFiles = [
		"test_service_proxy.py",
		"test_drover_proxy.py",
		"test_waygate_proxy.py",
		"test_waygate_agent.py",
		"test_lumen_proxy.py",
		"test_palimpsest_hub_proxy.py",
		"test_service_sdk_dependency_sources.py",
		"test_mcp_stage2_adapters.py",
		"test_ingress_root_path_coverage.py",
		"test_k3s_shell_proxy.py",
		"test_mcp_lumen_bridge.py"
	];

	for (const file of expectedContractFiles) {
		assert.ok(
			fs.existsSync(path.join(contractDir, file)),
			`contract test file ${file} must exist in backend/tests/contracts/`
		);
		assert.equal(
			fs.existsSync(path.join(rootDir, "backend", "tests", file)),
			false,
			`contract test file ${file} must no longer exist directly in backend/tests/`
		);
	}
});

test("live targets replace legacy integration target names", async () => {
	const targetsJs = require("./test-target.js");

	const liveTargets = ["live:auth", "live:admin", "live:compute", "live:network", "live:storage", "live:layers"];
	for (const name of liveTargets) {
		assert.ok(name in targetsJs.targets, `target ${name} must exist`);
		const legacyName = "integration:" + name.split(":")[1];
		assert.ok(!(legacyName in targetsJs.targets), `legacy target ${legacyName} must be removed`);
	}

	const result = await runCli(["integration:auth"]);
	assert.notEqual(result.code, 0, "running legacy integration:auth target must fail");
});
