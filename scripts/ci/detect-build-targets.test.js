const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
	ALL_TARGETS,
	collectAndDecide,
	collectEventChanges,
	decideTargets,
	main,
	targetsForFiles,
} = require("./detect-build-targets.js");

/** execFileSync 처럼 stderr 를 가진 명령 실패. */
function commandError(stderr) {
	const error = new Error(`Command failed: docker buildx imagetools inspect\n${stderr}`);
	error.stderr = stderr;
	return error;
}

const BEFORE = "1".repeat(40);
const HEAD = "2".repeat(40);
const PUB = "3".repeat(40);
const ZERO = "0".repeat(40);
const REPO = "openstack-afterglow/openstack-afterglow";

function config(revision) {
	return { architecture: "amd64", config: { Labels: revision ? { "org.opencontainers.image.revision": revision } : {} } };
}

function fakeExec(routes) {
	const calls = [];
	const exec = (cmd, args) => {
		const key = [cmd, ...args].join(" ");
		calls.push(key);
		for (const [match, response] of routes) {
			if (typeof match === "string" ? key === match : match.test(key)) {
				if (response instanceof Error) throw response;
				return response;
			}
		}
		throw new Error(`unexpected command: ${key}`);
	};
	exec.calls = calls;
	return exec;
}

function devPushEnv(overrides = {}) {
	return {
		GITHUB_EVENT_NAME: "push",
		EFFECTIVE_REF: "refs/heads/dev",
		GITHUB_SHA: HEAD,
		GITHUB_REPOSITORY: REPO,
		EVENT_BEFORE: BEFORE,
		EVENT_FORCED: "false",
		REGISTRY: "ghcr.io",
		IMAGE_OWNER: "openstack-afterglow",
		...overrides,
	};
}

const fetchBefore = [`git fetch --no-tags --depth=1 origin ${BEFORE}`, ""];
const diffBefore = (files) => [`git diff --name-only ${BEFORE} ${HEAD}`, files.join("\n")];
const inspect = (image, response) => [
	`docker buildx imagetools inspect ghcr.io/openstack-afterglow/${image}:dev --format {{json .Image}}`,
	response,
];
const allUnlabeled = [/imagetools inspect/, JSON.stringify(config())];

test("path rules keep the Afterglow deployment set coupling", () => {
	assert.deepEqual(targetsForFiles(["backend/app/main.py"]), ["backend", "frontend", "worker"]);
	assert.deepEqual(targetsForFiles(["services/afterglow-crypto/x.py"]), ["backend", "frontend", "worker"]);
	assert.deepEqual(targetsForFiles(["frontend/src/app.html"]), ["frontend"]);
	assert.deepEqual(targetsForFiles(["cloud-shell/bootstrap.sh"]), ["cloud-shell"]);
	assert.deepEqual(targetsForFiles(["Dockerfile"]), ALL_TARGETS);
	assert.deepEqual(targetsForFiles([".dockerignore"]), ALL_TARGETS);
	assert.deepEqual(targetsForFiles([".github/workflows/docker-build.yml"]), ALL_TARGETS);
	assert.deepEqual(targetsForFiles(["docs/index.md", "README.md", ".github/workflows/test.yml"]), []);
	assert.deepEqual(targetsForFiles(["xbackend/file", "frontend-notes.md", "Dockerfile.dev"]), []);
});

test("workflow_dispatch maps the requested set and rejects unknown values", () => {
	const decide = (dispatchTargets) =>
		decideTargets({ eventName: "workflow_dispatch", ref: "refs/heads/dev", dispatchTargets }).targets;
	assert.deepEqual(decide("backend"), ["backend"]);
	assert.deepEqual(decide("frontend"), ["frontend"]);
	assert.deepEqual(decide("worker"), ["worker"]);
	assert.deepEqual(decide("cloud-shell"), ["cloud-shell"]);
	assert.deepEqual(decide("afterglow"), ALL_TARGETS);
	assert.deepEqual(decide("all"), ALL_TARGETS);
	assert.throws(() => decide("database"), /Unsupported dispatch target: database/);
});

test("main, tags and pull requests build every target without git, registry or API access", () => {
	for (const [eventName, ref] of [
		["push", "refs/heads/main"],
		["push", "refs/tags/v1.2.3"],
		["pull_request", "refs/pull/78/merge"],
	]) {
		// 어떤 명령도 허용하지 않는 fake exec: PR 은 diff 를 계산하지 않는다(PR 은 빌드하지 않는다).
		const exec = fakeExec([]);
		const result = collectAndDecide(
			{ GITHUB_EVENT_NAME: eventName, EFFECTIVE_REF: ref, GITHUB_SHA: HEAD, EVENT_BEFORE: BEFORE, IMAGE_OWNER: "o" },
			exec,
		);
		assert.deepEqual(result.targets, ALL_TARGETS, `${eventName} ${ref}`);
		assert.deepEqual(exec.calls, [], `${eventName} ${ref}`);
	}
	assert.equal(collectEventChanges({ eventName: "pull_request", sha: HEAD }, fakeExec([])).files, null);
});

test("dev push diffs github.event.before..HEAD, never only the tip commit", () => {
	const exec = fakeExec([fetchBefore, diffBefore(["frontend/src/a.ts"]), allUnlabeled]);
	const result = collectAndDecide(devPushEnv(), exec);
	assert.deepEqual(result.targets, ["frontend"]);
	assert.ok(exec.calls.includes(`git fetch --no-tags --depth=1 origin ${BEFORE}`));
	assert.equal(exec.calls.some((call) => call.includes("HEAD^1")), false);
});

test("a multi-commit dev push that touched backend in an earlier commit still builds backend", () => {
	// before..HEAD 는 모든 push 커밋을 포함한다. 과거 tip-only diff 는 마지막 커밋(frontend)만 봤다.
	const exec = fakeExec([fetchBefore, diffBefore(["backend/app/api/deps.py", "frontend/src/a.ts"]), allUnlabeled]);
	assert.deepEqual(collectAndDecide(devPushEnv(), exec).targets, ["backend", "frontend", "worker"]);
});

test("zero before, forced push, fetch failure and diff failure build everything", () => {
	// 마지막 값: 예상하지 못한 기준 실패(::warning::)인지. 새 ref 와 forced push 는 예상된 경우라 조용하다.
	const cases = [
		[devPushEnv({ EVENT_BEFORE: ZERO }), [], false],
		[devPushEnv({ EVENT_BEFORE: "" }), [], false],
		[devPushEnv({ EVENT_FORCED: "true" }), [], false],
		[devPushEnv({ EVENT_BEFORE: "not-a-sha" }), [], true],
		[devPushEnv(), [[/git fetch/, new Error("fatal: remote error: upload-pack: not our ref")]], true],
		[devPushEnv(), [fetchBefore, [/git diff/, new Error("fatal: bad object")]], true],
	];
	for (const [env, routes, warns] of cases) {
		const exec = fakeExec(routes);
		const result = collectAndDecide(env, exec);
		assert.deepEqual(result.targets, ALL_TARGETS, JSON.stringify(result.reasons));
		assert.equal(exec.calls.some((call) => /^(docker|gh) /.test(call)), false);
		const basisWarnings = result.warnings.filter((warning) => warning.startsWith("Dev push event basis is unavailable"));
		assert.equal(basisWarnings.length, warns ? 1 : 0, JSON.stringify(result.warnings));
		if (warns) assert.ok(basisWarnings[0].includes(result.input.eventBasis), basisWarnings[0]);
	}
});

test("an unexpected event-basis failure is annotated, not only logged", () => {
	const lines = [];
	const exec = fakeExec([[/git fetch/, new Error("fatal: could not read Username for 'https://github.com'")]]);
	assert.equal(main(devPushEnv(), { exec, stdout: { write: (line) => lines.push(line) } }), 0);
	const output = lines.join("");
	assert.match(output, /^::warning title=Image target detection::Dev push event basis is unavailable \(fetch of before 1{40} failed: /m);
	assert.match(output, /^targets=\["backend","frontend","worker","cloud-shell"\]$/m);

	// main/태그/PR/dispatch 는 event 기준을 쓰지 않으므로 이 경고가 없다.
	for (const env of [
		{ GITHUB_EVENT_NAME: "push", EFFECTIVE_REF: "refs/heads/main", GITHUB_SHA: HEAD, EVENT_BEFORE: "not-a-sha" },
		{ GITHUB_EVENT_NAME: "pull_request", EFFECTIVE_REF: "refs/pull/1/merge", GITHUB_SHA: HEAD },
	]) {
		assert.deepEqual(collectAndDecide(env, fakeExec([])).warnings, [], JSON.stringify(env));
	}
});

test("docker-build.yml changes build everything on the event basis", () => {
	const exec = fakeExec([fetchBefore, diffBefore([".github/workflows/docker-build.yml"])]);
	assert.deepEqual(collectAndDecide(devPushEnv(), exec).targets, ALL_TARGETS);
});

test("no image paths and images that are not published (bootstrap) build nothing", () => {
	for (const response of [commandError("ERROR: manifest unknown"), commandError("ERROR: not found"), JSON.stringify(config())]) {
		const exec = fakeExec([fetchBefore, diffBefore(["docs/index.md"]), [/imagetools inspect/, response]]);
		const result = collectAndDecide(devPushEnv(), exec);
		assert.deepEqual(result.targets, [], String(response));
		assert.deepEqual(result.warnings, []);
		assert.equal(exec.calls.some((call) => call.startsWith("gh ")), false);
	}
});

test("a registry failure while reading published revisions builds those targets and warns", () => {
	for (const stderr of [
		"ERROR: failed to authorize: 401 Unauthorized",
		"ERROR: denied: requested access to the resource is denied",
		"ERROR: dial tcp: i/o timeout",
	]) {
		const exec = fakeExec([fetchBefore, diffBefore(["docs/index.md"]), [/imagetools inspect/, commandError(stderr)]]);
		const result = collectAndDecide(devPushEnv(), exec);
		assert.deepEqual(result.targets, ALL_TARGETS, stderr);
		assert.equal(result.warnings.length, ALL_TARGETS.length, stderr);
		assert.ok(result.warnings.every((warning) => warning.includes(stderr)), stderr);
	}

	// 일부 target 만 실패하면 그 target(과 배포 세트 규칙)만 추가로 빌드한다.
	const partial = fakeExec([
		fetchBefore,
		diffBefore(["docs/index.md"]),
		inspect("afterglow-api", JSON.stringify(config())),
		inspect("afterglow-worker", JSON.stringify(config())),
		inspect("afterglow", JSON.stringify(config())),
		inspect("afterglow-cloud-shell", commandError("ERROR: toomanyrequests: rate limit exceeded")),
	]);
	assert.deepEqual(collectAndDecide(devPushEnv(), partial).targets, ["cloud-shell"]);
});

test("a failed registry login is reported as a warning", () => {
	const lines = [];
	const exec = fakeExec([fetchBefore, diffBefore(["frontend/a.ts"]), [/imagetools inspect/, commandError("ERROR: 401 Unauthorized")]]);
	assert.equal(main(devPushEnv({ REGISTRY_LOGIN_OUTCOME: "failure" }), { exec, stdout: { write: (line) => lines.push(line) } }), 0);
	const output = lines.join("");
	assert.match(output, /^::warning title=Image target detection::Registry login failed/m);
	assert.match(output, /^::warning title=Image target detection::backend: published revision check failed/m);
	assert.match(output, /^targets=\["backend","frontend","worker","cloud-shell"\]$/m);

	const quiet = [];
	const ok = fakeExec([fetchBefore, diffBefore(["frontend/a.ts"]), allUnlabeled]);
	assert.equal(main(devPushEnv({ REGISTRY_LOGIN_OUTCOME: "success" }), { exec: ok, stdout: { write: (line) => quiet.push(line) } }), 0);
	assert.doesNotMatch(quiet.join(""), /::warning::|::warning /);
});

test("targets already selected by the event basis are not inspected", () => {
	const exec = fakeExec([fetchBefore, diffBefore(["frontend/src/a.ts"]), allUnlabeled]);
	collectAndDecide(devPushEnv(), exec);
	const inspected = exec.calls.filter((call) => call.includes("imagetools inspect"));
	assert.equal(inspected.some((call) => call.includes("/afterglow:dev")), false);
	assert.equal(inspected.length, 3);
});

test("published-revision basis rebuilds a target whose earlier build failed (carry-over)", () => {
	// 이전 실행에서 backend 빌드만 실패: backend :dev 는 PUB, worker/frontend 는 BEFORE 에서 발행됐다.
	const exec = fakeExec([
		fetchBefore,
		diffBefore(["docs/index.md"]),
		inspect("afterglow-api", JSON.stringify(config(PUB))),
		inspect("afterglow-worker", JSON.stringify(config(BEFORE))),
		inspect("afterglow", JSON.stringify(config(BEFORE))),
		inspect("afterglow-cloud-shell", JSON.stringify(config())),
		[`gh api repos/${REPO}/compare/${PUB}...${HEAD} --jq .status`, "ahead"],
		[`gh api repos/${REPO}/compare/${BEFORE}...${HEAD} --jq .status`, "ahead"],
		[`git fetch --no-tags --depth=1 origin ${PUB}`, ""],
		[`git diff --name-only ${PUB} ${HEAD}`, "backend/app/api/deps.py\ndocs/index.md"],
		[`git diff --name-only ${BEFORE} ${HEAD}`, "docs/index.md"],
	]);
	const result = collectAndDecide(devPushEnv(), exec);
	// backend 가 다시 빌드되고, 배포 세트 규칙으로 frontend 도 함께 빌드된다. worker 는 최신이다.
	assert.deepEqual(result.targets, ["backend", "frontend"]);
});

test("published revision identical to HEAD adds nothing", () => {
	const exec = fakeExec([
		fetchBefore,
		diffBefore(["docs/index.md"]),
		[/imagetools inspect/, JSON.stringify(config(HEAD))],
	]);
	assert.deepEqual(collectAndDecide(devPushEnv(), exec).targets, []);
	assert.equal(exec.calls.some((call) => call.startsWith("gh ")), false);
});

test("compare statuses: identical/ahead use the diff, behind falls back, diverged builds", () => {
	const run = (status, published = PUB) =>
		collectAndDecide(
			devPushEnv(),
			fakeExec([
				fetchBefore,
				diffBefore(["docs/index.md"]),
				inspect("afterglow-api", JSON.stringify(config())),
				inspect("afterglow-worker", JSON.stringify(config())),
				inspect("afterglow", JSON.stringify(config())),
				inspect("afterglow-cloud-shell", JSON.stringify(config(published))),
				[/gh api .*compare/, status],
				[`git fetch --no-tags --depth=1 origin ${published}`, ""],
				[`git diff --name-only ${published} ${HEAD}`, "cloud-shell/bootstrap.sh"],
			]),
		).targets;
	assert.deepEqual(run("ahead"), ["cloud-shell"]);
	assert.deepEqual(run("identical"), ["cloud-shell"]);
	assert.deepEqual(run("behind"), []);
	assert.deepEqual(run("diverged"), ["cloud-shell"]);
});

test("any error after a published revision is read builds that target", () => {
	const base = [
		fetchBefore,
		diffBefore(["docs/index.md"]),
		inspect("afterglow-api", JSON.stringify(config())),
		inspect("afterglow-worker", JSON.stringify(config())),
		inspect("afterglow", JSON.stringify(config(PUB))),
		inspect("afterglow-cloud-shell", JSON.stringify(config())),
	];
	const compareError = fakeExec([...base, [/compare/, new Error("HTTP 502")]]);
	assert.deepEqual(collectAndDecide(devPushEnv(), compareError).targets, ["frontend"]);

	const unknownStatus = fakeExec([...base, [/compare/, "weird"]]);
	assert.deepEqual(collectAndDecide(devPushEnv(), unknownStatus).targets, ["frontend"]);

	const fetchError = fakeExec([...base, [/compare/, "ahead"], [`git fetch --no-tags --depth=1 origin ${PUB}`, new Error("not our ref")]]);
	assert.deepEqual(collectAndDecide(devPushEnv(), fetchError).targets, ["frontend"]);

	const diffError = fakeExec([
		...base,
		[/compare/, "ahead"],
		[`git fetch --no-tags --depth=1 origin ${PUB}`, ""],
		[`git diff --name-only ${PUB} ${HEAD}`, new Error("bad object")],
	]);
	assert.deepEqual(collectAndDecide(devPushEnv(), diffError).targets, ["frontend"]);
});

test("a docker-build.yml change since the published revision rebuilds that target", () => {
	const exec = fakeExec([
		fetchBefore,
		diffBefore(["docs/index.md"]),
		inspect("afterglow-api", JSON.stringify(config())),
		inspect("afterglow-worker", JSON.stringify(config(PUB))),
		inspect("afterglow", JSON.stringify(config())),
		inspect("afterglow-cloud-shell", JSON.stringify(config())),
		[/compare/, "ahead"],
		[`git fetch --no-tags --depth=1 origin ${PUB}`, ""],
		[`git diff --name-only ${PUB} ${HEAD}`, ".github/workflows/docker-build.yml"],
	]);
	// worker 가 선택되면 배포 세트 규칙으로 frontend 도 함께 빌드한다.
	assert.deepEqual(collectAndDecide(devPushEnv(), exec).targets, ["frontend", "worker"]);
});

test("a frontend published revision behind a backend change rebuilds frontend", () => {
	const exec = fakeExec([
		fetchBefore,
		diffBefore(["docs/index.md"]),
		inspect("afterglow-api", JSON.stringify(config())),
		inspect("afterglow-worker", JSON.stringify(config())),
		inspect("afterglow", JSON.stringify(config(PUB))),
		inspect("afterglow-cloud-shell", JSON.stringify(config())),
		[/compare/, "ahead"],
		[`git fetch --no-tags --depth=1 origin ${PUB}`, ""],
		[`git diff --name-only ${PUB} ${HEAD}`, "backend/app/main.py"],
	]);
	assert.deepEqual(collectAndDecide(devPushEnv(), exec).targets, ["frontend"]);
});

test("main writes targets, standard_targets and cloud_shell to GITHUB_OUTPUT", () => {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "detect-targets-"));
	const output = path.join(dir, "out");
	try {
		const exec = fakeExec([fetchBefore, diffBefore(["cloud-shell/x", "frontend/y"]), allUnlabeled]);
		const stdout = { write: () => {} };
		assert.equal(main(devPushEnv({ GITHUB_OUTPUT: output }), { exec, stdout }), 0);
		assert.equal(
			fs.readFileSync(output, "utf8"),
			'targets=["frontend","cloud-shell"]\nstandard_targets=["frontend"]\ncloud_shell=true\n',
		);

		const bad = path.join(dir, "bad");
		const lines = [];
		assert.equal(
			main({ GITHUB_EVENT_NAME: "workflow_dispatch", EFFECTIVE_REF: "refs/heads/dev", DISPATCH_TARGETS: "db", GITHUB_OUTPUT: bad }, {
				exec: fakeExec([]),
				stdout: { write: (line) => lines.push(line) },
			}),
			1,
		);
		assert.match(lines.join(""), /::error::Unsupported dispatch target: db/);
		assert.equal(fs.existsSync(bad), false);
	} finally {
		fs.rmSync(dir, { recursive: true, force: true });
	}
});
