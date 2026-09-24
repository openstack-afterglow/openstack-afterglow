const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { decidePublish, main } = require("./helm-publish-decision.js");

const BEFORE = "1".repeat(40);
const HEAD = "2".repeat(40);
const ZERO = "0".repeat(40);

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

function mainPush(overrides = {}) {
	return {
		GITHUB_EVENT_NAME: "push",
		GITHUB_REF: "refs/heads/main",
		GITHUB_REF_TYPE: "branch",
		GITHUB_SHA: HEAD,
		EVENT_BEFORE: BEFORE,
		EVENT_FORCED: "false",
		...overrides,
	};
}

const fetchBefore = [`git fetch --no-tags --depth=1 origin ${BEFORE}`, ""];
const diffBefore = (files) => [`git diff --no-renames --name-only ${BEFORE} ${HEAD}`, files.join("\n")];

test("a multi-commit main push whose earlier commit touched the chart publishes", () => {
	// before..HEAD 는 push 의 모든 커밋을 포함한다. 과거 tip-only diff 는 마지막 커밋(docs)만 봤다.
	const exec = fakeExec([fetchBefore, diffBefore(["helm/afterglow/values.yaml", "docs/index.md"])]);
	const result = decidePublish(mainPush(), exec);
	assert.equal(result.publish, true);
	assert.deepEqual(result.files, ["helm/afterglow/values.yaml"]);
	assert.ok(exec.calls.includes(`git diff --no-renames --name-only ${BEFORE} ${HEAD}`));
	assert.equal(exec.calls.some((call) => call.includes("HEAD^1")), false);
});

test("a main push without chart changes skips the publish", () => {
	for (const files of [[], ["docs/index.md", "helm/README.md", "helm/afterglow-notes.md", "deploy/helm/afterglow/x"]]) {
		const result = decidePublish(mainPush(), fakeExec([fetchBefore, diffBefore(files)]));
		assert.equal(result.publish, false, JSON.stringify(files));
		assert.deepEqual(result.warnings, []);
	}
});

test("a chart file moved out of helm/afterglow/ publishes", () => {
	// `--no-renames` 는 rename 을 삭제+추가로 보고한다. 기본 rename 감지는 도착 경로만 보고해 발행을 놓친다.
	const exec = fakeExec([fetchBefore, diffBefore(["archive/configmap.yaml", "helm/afterglow/templates/configmap.yaml"])]);
	const result = decidePublish(mainPush(), exec);
	assert.equal(result.publish, true);
	assert.deepEqual(result.files, ["helm/afterglow/templates/configmap.yaml"]);
});

test("zero before, forced push, invalid before, fetch and diff failures publish", () => {
	const cases = [
		[mainPush({ EVENT_BEFORE: ZERO }), [], false],
		[mainPush({ EVENT_BEFORE: "" }), [], false],
		[mainPush({ EVENT_FORCED: "true" }), [], false],
		[mainPush({ EVENT_BEFORE: "not-a-sha" }), [], true],
		[mainPush(), [[/git fetch/, new Error("fatal: remote error: upload-pack: not our ref")]], true],
		[mainPush(), [fetchBefore, [/git diff/, new Error("fatal: bad object")]], true],
	];
	for (const [env, routes, warns] of cases) {
		const result = decidePublish(env, fakeExec(routes));
		assert.equal(result.publish, true, JSON.stringify(result.reasons));
		assert.equal(result.warnings.length, warns ? 1 : 0, JSON.stringify(result.warnings));
	}
});

test("tags and workflow_dispatch always publish without git", () => {
	for (const env of [
		{ GITHUB_EVENT_NAME: "push", GITHUB_REF: "refs/tags/v1.2.3", GITHUB_REF_TYPE: "tag", GITHUB_SHA: HEAD, EVENT_BEFORE: BEFORE },
		{ GITHUB_EVENT_NAME: "workflow_dispatch", GITHUB_REF: "refs/heads/main", GITHUB_SHA: HEAD },
		{ GITHUB_EVENT_NAME: "", GITHUB_REF: "", GITHUB_SHA: "" },
	]) {
		const exec = fakeExec([]);
		assert.equal(decidePublish(env, exec).publish, true, JSON.stringify(env));
		assert.deepEqual(exec.calls, []);
	}
});

test("main writes publish exactly once, annotates unexpected failures and never exits non-zero", () => {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "helm-publish-"));
	try {
		const run = (env, exec) => {
			const output = path.join(dir, `out-${Math.random().toString(16).slice(2)}`);
			const lines = [];
			const code = main({ ...env, GITHUB_OUTPUT: output }, { exec, stdout: { write: (line) => lines.push(line) } });
			return { code, stdout: lines.join(""), output: fs.readFileSync(output, "utf8") };
		};

		const skipped = run(mainPush(), fakeExec([fetchBefore, diffBefore(["docs/index.md"])]));
		assert.equal(skipped.code, 0);
		assert.equal(skipped.output, "publish=false\n");
		assert.doesNotMatch(skipped.stdout, /::warning/);

		const published = run(mainPush(), fakeExec([fetchBefore, diffBefore(["helm/afterglow/Chart.yaml"])]));
		assert.equal(published.output, "publish=true\n");

		const fetchFailed = run(mainPush(), fakeExec([[/git fetch/, new Error("fatal: could not read from remote")]]));
		assert.equal(fetchFailed.code, 0);
		assert.equal(fetchFailed.output, "publish=true\n");
		assert.match(fetchFailed.stdout, /^::warning title=Helm chart publish::Push basis is unavailable \(fetch of before 1{40} failed: /m);

		const thrown = run(mainPush(), () => {
			throw "boom";
		});
		assert.equal(thrown.code, 0);
		assert.equal(thrown.output, "publish=true\n");
	} finally {
		fs.rmSync(dir, { recursive: true, force: true });
	}
});

// ─── 실제 git: chart 파일을 helm/afterglow/ 밖으로 옮긴 main push ─────────────────────────
const GIT_ENV = {
	...process.env,
	GIT_CONFIG_GLOBAL: "/dev/null",
	GIT_CONFIG_NOSYSTEM: "1",
	GIT_AUTHOR_NAME: "ci",
	GIT_AUTHOR_EMAIL: "ci@example.invalid",
	GIT_COMMITTER_NAME: "ci",
	GIT_COMMITTER_EMAIL: "ci@example.invalid",
	GIT_TERMINAL_PROMPT: "0",
};

function git(cwd, ...args) {
	return execFileSync("git", args, { cwd, env: GIT_ENV, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

test("real git: a chart file moved out of helm/afterglow/ publishes", () => {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "helm-publish-git-"));
	const origin = path.join(dir, "origin");
	const workspace = path.join(dir, "workspace");
	const from = "helm/afterglow/templates/configmap.yaml";
	const to = "archive/configmap.yaml";
	try {
		fs.mkdirSync(path.join(origin, path.dirname(from)), { recursive: true });
		git(origin, "init", "-q", "-b", "main");
		git(origin, "config", "uploadpack.allowReachableSHA1InWant", "true");
		// 여러 줄 내용이어야 git 이 rename 으로 짝짓는다(빈 파일은 flag 유무와 무관하게 통과한다).
		fs.writeFileSync(path.join(origin, from), Array.from({ length: 12 }, (_, i) => `key${i}: value ${i}\n`).join(""));
		git(origin, "add", ".");
		git(origin, "commit", "-q", "-m", "A");
		const before = git(origin, "rev-parse", "HEAD");
		fs.mkdirSync(path.join(origin, "archive"));
		git(origin, "mv", from, to);
		git(origin, "commit", "-q", "-m", "B");
		const head = git(origin, "rev-parse", "HEAD");
		assert.equal(git(origin, "diff", "--name-only", before, head), to, "fixture: default rename detection reports only the destination");

		fs.mkdirSync(workspace);
		git(workspace, "init", "-q", "-b", "main");
		git(workspace, "remote", "add", "origin", `file://${origin}`);
		git(workspace, "fetch", "-q", "--no-tags", "--depth=1", "origin", head);
		git(workspace, "checkout", "-q", "--detach", "FETCH_HEAD");

		const exec = (cmd, args) => {
			assert.equal(cmd, "git");
			return execFileSync("git", args, { cwd: workspace, env: GIT_ENV, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
		};
		const result = decidePublish(mainPush({ GITHUB_SHA: head, EVENT_BEFORE: before }), exec);
		assert.equal(result.publish, true, JSON.stringify(result.reasons));
		assert.deepEqual(result.files, [from]);
	} finally {
		fs.rmSync(dir, { recursive: true, force: true });
	}
});
