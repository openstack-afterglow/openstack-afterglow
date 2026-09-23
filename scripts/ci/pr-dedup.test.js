const assert = require("node:assert/strict");
const { execFileSync, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { decide, main } = require("./pr-dedup.js");

const SCRIPT = path.join(__dirname, "pr-dedup.js");
const REPO = "openstack-afterglow/openstack-afterglow";
const HEAD = "2".repeat(40);
const TREE = "a".repeat(40);
const OTHER_TREE = "b".repeat(40);

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

const fetchHead = [`git fetch --no-tags --depth=1 origin ${HEAD}`, ""];
const mergeTree = (tree) => ["git rev-parse HEAD^{tree}", `${tree}\n`];
const headTree = (tree) => [`git rev-parse ${HEAD}^{tree}`, `${tree}\n`];

function sameRepoDev(overrides = {}) {
	return {
		HEAD_REPO: REPO,
		BASE_REPO: REPO,
		HEAD_REF: "dev",
		HEAD_SHA: HEAD,
		PR_AUTHOR: "jung-geun",
		GITHUB_SERVER_URL: "https://github.com",
		...overrides,
	};
}

/** main() 을 실행하고 stdout 과 GITHUB_OUTPUT 내용을 돌려준다. */
function run(env, exec) {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pr-dedup-"));
	const output = path.join(dir, "out");
	const lines = [];
	try {
		const code = main({ ...env, GITHUB_OUTPUT: output }, { exec, stdout: { write: (line) => lines.push(line) } });
		return { code, stdout: lines.join(""), output: fs.existsSync(output) ? fs.readFileSync(output, "utf8") : "" };
	} finally {
		fs.rmSync(dir, { recursive: true, force: true });
	}
}

test("a same-repo dev PR whose merge tree equals the head tree is skipped with a commit link", () => {
	const exec = fakeExec([fetchHead, mergeTree(TREE), headTree(TREE)]);
	const result = run(sameRepoDev(), exec);
	assert.equal(result.code, 0);
	assert.equal(result.output, "skip=true\n");
	assert.match(result.stdout, /^::notice title=Layered Tests deduplicated::PR merge tree a{40} equals dev head 2{40} tree/m);
	assert.ok(result.stdout.includes(`https://github.com/${REPO}/commit/${HEAD}`), result.stdout);
});

test("fork, dependabot, non-dev and malformed-SHA PRs are tested without touching git", () => {
	const cases = [
		["fork PR from a branch named dev", { HEAD_REPO: "attacker/openstack-afterglow" }],
		["unknown head repository", { HEAD_REPO: "" }],
		["unknown base repository", { BASE_REPO: "" }],
		["dependabot head ref", { HEAD_REF: "dependabot/npm_and_yarn/frontend/vite-7.1.0" }],
		["dependabot author on dev", { PR_AUTHOR: "dependabot[bot]" }],
		["feature branch", { HEAD_REF: "feature/x" }],
		["dev-like branch", { HEAD_REF: "dev2" }],
		["empty head ref", { HEAD_REF: "" }],
		["empty SHA", { HEAD_SHA: "" }],
		["short SHA", { HEAD_SHA: "abc123" }],
		["upper-case SHA", { HEAD_SHA: "A".repeat(40) }],
		["SHA with a trailing newline", { HEAD_SHA: `${HEAD}\n` }],
		["SHA with an option prefix", { HEAD_SHA: `--upload-pack=${"a".repeat(24)}` }],
	];
	for (const [label, overrides] of cases) {
		const exec = fakeExec([]);
		const result = run(sameRepoDev(overrides), exec);
		assert.equal(result.code, 0, label);
		assert.equal(result.output, "skip=false\n", label);
		assert.deepEqual(exec.calls, [], label);
		assert.doesNotMatch(result.stdout, /::notice/, label);
	}
});

test("differing trees are tested", () => {
	const result = run(sameRepoDev(), fakeExec([fetchHead, mergeTree(TREE), headTree(OTHER_TREE)]));
	assert.equal(result.output, "skip=false\n");
	assert.match(result.stdout, /differs from head tree/);
});

test("empty or malformed tree hashes never count as equal", () => {
	for (const tree of ["", "not-a-tree", "A".repeat(40)]) {
		const result = run(sameRepoDev(), fakeExec([fetchHead, mergeTree(tree), headTree(tree)]));
		assert.equal(result.output, "skip=false\n", JSON.stringify(tree));
	}
});

test("fetch and rev-parse failures run the tests and warn", () => {
	const cases = [
		[[/git fetch/, new Error("fatal: remote error: upload-pack: not our ref")]],
		[fetchHead, ["git rev-parse HEAD^{tree}", new Error("fatal: ambiguous argument")]],
		[fetchHead, mergeTree(TREE), [/rev-parse 2{40}/, new Error("fatal: bad object")]],
	];
	for (const routes of cases) {
		const result = run(sameRepoDev(), fakeExec(routes));
		assert.equal(result.code, 0);
		assert.equal(result.output, "skip=false\n");
		assert.match(result.stdout, /^::warning title=PR dedup::PR dedup check failed \(/m);
	}
	// Error 가 아닌 값을 throw 해도 skip=false 다.
	const odd = run(sameRepoDev(), () => {
		throw "boom";
	});
	assert.equal(odd.output, "skip=false\n");
});

test("decide returns true only for equal valid trees", () => {
	assert.equal(decide({ headRepo: REPO, baseRepo: REPO, headRef: "dev", headSha: HEAD }, fakeExec([fetchHead, mergeTree(TREE), headTree(TREE)])).skip, true);
	assert.equal(decide({ headRepo: REPO, baseRepo: REPO, headRef: "dev", headSha: HEAD }, fakeExec([fetchHead, mergeTree(TREE), headTree(OTHER_TREE)])).skip, false);
	assert.equal(decide({}, fakeExec([])).skip, false);
});

// ─── 실제 git: PR merge commit checkout 을 흉내 낸 scratch clone 에서 CLI 를 실행한다 ─────────────
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

/**
 * origin: main=A, dev=A+B. divergedMain 이면 main 에 C 를 더한다. PR merge commit 은 main 에 dev 를 --no-ff 로 병합한다.
 * workspace 는 actions/checkout(fetch-depth: 1)처럼 merge commit 만 얕게 가져와 detached checkout 한다.
 */
function scratchPr({ divergedMain }) {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pr-dedup-git-"));
	const origin = path.join(dir, "origin");
	const workspace = path.join(dir, "workspace");
	fs.mkdirSync(origin);
	git(origin, "init", "-q", "-b", "main");
	fs.writeFileSync(path.join(origin, "a.txt"), "a\n");
	git(origin, "add", "a.txt");
	git(origin, "commit", "-q", "-m", "A");
	git(origin, "switch", "-q", "-c", "dev");
	fs.writeFileSync(path.join(origin, "b.txt"), "b\n");
	git(origin, "add", "b.txt");
	git(origin, "commit", "-q", "-m", "B");
	const devSha = git(origin, "rev-parse", "HEAD");
	git(origin, "switch", "-q", "main");
	if (divergedMain) {
		fs.writeFileSync(path.join(origin, "c.txt"), "c\n");
		git(origin, "add", "c.txt");
		git(origin, "commit", "-q", "-m", "C");
	}
	git(origin, "merge", "-q", "--no-ff", "dev", "-m", "merge dev");
	const mergeSha = git(origin, "rev-parse", "HEAD");
	git(origin, "update-ref", "refs/pull/1/merge", mergeSha);
	git(origin, "switch", "-q", "dev");

	fs.mkdirSync(workspace);
	git(workspace, "init", "-q", "-b", "main");
	git(workspace, "remote", "add", "origin", `file://${origin}`);
	git(workspace, "fetch", "-q", "--no-tags", "--depth=1", "origin", "refs/pull/1/merge");
	git(workspace, "checkout", "-q", "--detach", "FETCH_HEAD");
	return { dir, workspace, devSha };
}

function runCli(workspace, env) {
	const output = path.join(workspace, "..", "github-output");
	fs.writeFileSync(output, "");
	const result = spawnSync(process.execPath, [SCRIPT], {
		cwd: workspace,
		env: { ...GIT_ENV, ...env, GITHUB_OUTPUT: output },
		encoding: "utf8",
		timeout: 60_000,
	});
	return { status: result.status, stdout: result.stdout, stderr: result.stderr, output: fs.readFileSync(output, "utf8") };
}

test("real git: equal merge and head trees skip, and every other case tests", () => {
	const same = scratchPr({ divergedMain: false });
	const diverged = scratchPr({ divergedMain: true });
	try {
		const base = { HEAD_REPO: REPO, BASE_REPO: REPO, HEAD_REF: "dev", PR_AUTHOR: "jung-geun", GITHUB_SERVER_URL: "https://github.com" };

		const skipped = runCli(same.workspace, { ...base, HEAD_SHA: same.devSha });
		assert.equal(skipped.status, 0, skipped.stderr);
		assert.equal(skipped.output, "skip=true\n", skipped.stdout);
		assert.ok(skipped.stdout.includes(`/commit/${same.devSha}`), skipped.stdout);

		const fork = runCli(same.workspace, { ...base, HEAD_REPO: "attacker/openstack-afterglow", HEAD_SHA: same.devSha });
		assert.equal(fork.output, "skip=false\n", fork.stdout);

		const dependabot = runCli(same.workspace, { ...base, HEAD_REF: "dependabot/npm_and_yarn/x", HEAD_SHA: same.devSha });
		assert.equal(dependabot.output, "skip=false\n", dependabot.stdout);

		const malformed = runCli(same.workspace, { ...base, HEAD_SHA: "HEAD" });
		assert.equal(malformed.output, "skip=false\n", malformed.stdout);

		const unfetchable = runCli(same.workspace, { ...base, HEAD_SHA: "f".repeat(40) });
		assert.equal(unfetchable.status, 0, unfetchable.stderr);
		assert.equal(unfetchable.output, "skip=false\n", unfetchable.stdout);
		assert.match(unfetchable.stdout, /::warning title=PR dedup::/);

		const differs = runCli(diverged.workspace, { ...base, HEAD_SHA: diverged.devSha });
		assert.equal(differs.status, 0, differs.stderr);
		assert.equal(differs.output, "skip=false\n", differs.stdout);
		assert.match(differs.stdout, /differs from head tree/);
	} finally {
		fs.rmSync(same.dir, { recursive: true, force: true });
		fs.rmSync(diverged.dir, { recursive: true, force: true });
	}
});
