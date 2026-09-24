const assert = require("node:assert/strict");
const test = require("node:test");

const {
	GUARD_SKIP_EXIT,
	branchNameOf,
	branchTip,
	compareStatus,
	guardDecision,
	inspectPinned,
	main,
	parseDigest,
	parseRevisionLabel,
	readRevision,
	repositoryOf,
} = require("./image-revision.js");

const SHA_A = "a".repeat(40);
const SHA_B = "b".repeat(40);
const SHA_C = "c".repeat(40);
const DEV_REF = "refs/heads/dev";
const TIP_KEY = `gh api repos/openstack-afterglow/openstack-afterglow/git/ref/heads/dev --jq .object.sha`;
const DIGEST = `sha256:${"c".repeat(64)}`;
const REPO = "openstack-afterglow/openstack-afterglow";

function config(revision) {
	const labels = revision === undefined ? {} : { "org.opencontainers.image.revision": revision };
	return { architecture: "amd64", os: "linux", config: { Labels: labels } };
}

/** execFileSync 처럼 stderr 를 가진 명령 실패. */
function commandError(stderr) {
	const error = new Error(`Command failed: docker buildx imagetools inspect\n${stderr}`);
	error.stderr = stderr;
	return error;
}

/** 호출을 기록하고 key(cmd + args)별 응답 또는 예외를 돌려주는 fake exec. */
function fakeExec(routes) {
	const calls = [];
	const exec = (cmd, args) => {
		const key = [cmd, ...args].join(" ");
		calls.push(key);
		for (const [match, response] of routes) {
			if (typeof match === "string" ? key === match : match.test(key)) {
				if (response instanceof Error) throw response;
				return typeof response === "function" ? response(key) : response;
			}
		}
		throw new Error(`unexpected command: ${key}`);
	};
	exec.calls = calls;
	return exec;
}

function sink() {
	const chunks = [];
	return { write: (chunk) => chunks.push(String(chunk)), text: () => chunks.join("") };
}

test("parseRevisionLabel reads a single-platform image config", () => {
	assert.equal(parseRevisionLabel(JSON.stringify(config(SHA_A))), SHA_A);
	assert.equal(parseRevisionLabel(JSON.stringify(config(SHA_A.toUpperCase()))), SHA_A);
});

test("parseRevisionLabel reads a platform-keyed map from a multi-platform index", () => {
	const map = { "linux/amd64": config(SHA_A), "linux/arm64": config(SHA_A) };
	assert.equal(parseRevisionLabel(JSON.stringify(map)), SHA_A);
});

test("parseRevisionLabel returns null only when the label is missing", () => {
	assert.equal(parseRevisionLabel(""), null);
	assert.equal(parseRevisionLabel("null"), null);
	assert.equal(parseRevisionLabel(JSON.stringify(config())), null);
	assert.equal(parseRevisionLabel(JSON.stringify({ architecture: "amd64", config: {} })), null);
});

test("parseRevisionLabel rejects a label that is not a commit SHA", () => {
	assert.throws(() => parseRevisionLabel(JSON.stringify(config("not-a-sha"))), /malformed/);
	assert.throws(() => parseRevisionLabel(JSON.stringify(config("$(touch /tmp/x)"))), /malformed/);
});

test("parseRevisionLabel rejects platforms that disagree", () => {
	const map = { "linux/amd64": config(SHA_A), "linux/arm64": config(SHA_B) };
	assert.throws(() => parseRevisionLabel(JSON.stringify(map)), /disagree/);
});

test("parseDigest reads the Digest line of the default inspect output", () => {
	const output = [
		"Name:      ghcr.io/o/afterglow-api:dev-amd64",
		"MediaType: application/vnd.oci.image.index.v1+json",
		`Digest:    ${DIGEST}`,
		"",
		"Manifests:",
		`  Name:      ghcr.io/o/afterglow-api:dev-amd64@sha256:${"d".repeat(64)}`,
	].join("\n");
	assert.equal(parseDigest(output), DIGEST);
	assert.throws(() => parseDigest("Name: x\n"), /no Digest line/);
	assert.throws(() => parseDigest("Digest:    sha256:zz\n"), /malformed digest/);
});

test("repositoryOf strips tags and digests but keeps registry ports", () => {
	assert.equal(repositoryOf("ghcr.io/o/afterglow-api:dev-amd64"), "ghcr.io/o/afterglow-api");
	assert.equal(repositoryOf(`ghcr.io/o/afterglow-api@${DIGEST}`), "ghcr.io/o/afterglow-api");
	assert.equal(repositoryOf("registry.local:5000/o/afterglow:dev"), "registry.local:5000/o/afterglow");
	assert.equal(repositoryOf("registry.local:5000/o/afterglow"), "registry.local:5000/o/afterglow");
});

test("readRevision reports a present label", () => {
	const exec = fakeExec([[/imagetools inspect/, JSON.stringify(config(SHA_A))]]);
	assert.deepEqual(readRevision("ghcr.io/o/afterglow:dev", exec), { kind: "present", revision: SHA_A });
});

test("readRevision reports absent only for a missing image or a missing label", () => {
	const ref = "ghcr.io/o/afterglow:dev";
	for (const stderr of [
		`ERROR: ${ref}: not found`,
		"ERROR: manifest unknown: manifest unknown",
		"ERROR: name unknown: repository name not known to registry",
	]) {
		assert.equal(readRevision(ref, fakeExec([[/imagetools inspect/, commandError(stderr)]])).kind, "absent", stderr);
	}
	assert.equal(readRevision(ref, fakeExec([[/imagetools inspect/, new Error("manifest unknown")]])).kind, "absent");
	const unlabeled = readRevision(ref, fakeExec([[/imagetools inspect/, JSON.stringify(config())]]));
	assert.equal(unlabeled.kind, "absent");
	assert.match(unlabeled.reason, /no org\.opencontainers\.image\.revision label/);
});

test("readRevision reports registry, transport and format failures as errors, not absence", () => {
	const ref = "ghcr.io/o/afterglow:dev";
	for (const stderr of [
		"ERROR: failed to authorize: failed to fetch anonymous token: 401 Unauthorized",
		"ERROR: denied: requested access to the resource is denied",
		"ERROR: unexpected status from HEAD request: 403 Forbidden (not found in cache)",
		"ERROR: dial tcp: lookup ghcr.io: i/o timeout",
		"ERROR: toomanyrequests: rate limit exceeded",
	]) {
		const result = readRevision(ref, fakeExec([[/imagetools inspect/, commandError(stderr)]]));
		assert.equal(result.kind, "error", stderr);
		assert.ok(result.reason.includes(stderr), result.reason);
	}
	const timeout = Object.assign(new Error("spawnSync docker ETIMEDOUT"), { code: "ETIMEDOUT" });
	assert.equal(readRevision(ref, fakeExec([[/imagetools inspect/, timeout]])).kind, "error");
	assert.equal(readRevision(ref, fakeExec([[/imagetools inspect/, "{not json"]])).kind, "error");
	assert.equal(readRevision(ref, fakeExec([[/imagetools inspect/, JSON.stringify(config("v1.2.3"))]])).kind, "error");
	const disagree = JSON.stringify({ "linux/amd64": config(SHA_A), "linux/arm64": config(SHA_B) });
	assert.equal(readRevision(ref, fakeExec([[/imagetools inspect/, disagree]])).kind, "error");
});

test("inspectPinned reads the label from the digest it resolved", () => {
	const exec = fakeExec([
		["docker buildx imagetools inspect ghcr.io/o/afterglow-api:dev-amd64", `Name: x\nDigest:    ${DIGEST}\n`],
		[`docker buildx imagetools inspect ghcr.io/o/afterglow-api@${DIGEST} --format {{json .Image}}`, JSON.stringify(config(SHA_A))],
	]);
	assert.deepEqual(inspectPinned("ghcr.io/o/afterglow-api:dev-amd64", exec), {
		digest: DIGEST,
		pinned: `ghcr.io/o/afterglow-api@${DIGEST}`,
		revision: SHA_A,
	});
});

test("compareStatus validates inputs and the returned status", () => {
	const ok = fakeExec([[`gh api repos/${REPO}/compare/${SHA_A}...${SHA_B} --jq .status`, "ahead\n"]]);
	assert.equal(compareStatus(REPO, SHA_A, SHA_B, ok), "ahead");
	assert.throws(() => compareStatus(REPO, "HEAD", SHA_B, ok), /full commit SHAs/);
	assert.throws(() => compareStatus("bad repo;rm", SHA_A, SHA_B, ok), /invalid repository/);
	const weird = fakeExec([[/gh api/, "\n"]]);
	assert.throws(() => compareStatus(REPO, SHA_A, SHA_B, weird), /unexpected compare status/);
});

test("branchNameOf accepts only refs/heads/<name>", () => {
	assert.equal(branchNameOf("refs/heads/dev"), "dev");
	assert.equal(branchNameOf("refs/heads/release/1.2"), "release/1.2");
	for (const bad of ["dev", "refs/tags/v1.2.3", "refs/heads/", "refs/heads/../main", "refs/heads/a;touch x", "", undefined]) {
		assert.equal(branchNameOf(bad), null, String(bad));
	}
});

test("branchTip reads the ref through the GitHub API and validates the SHA", () => {
	assert.equal(branchTip(REPO, DEV_REF, fakeExec([[TIP_KEY, `${SHA_C.toUpperCase()}\n`]])), SHA_C);
	assert.throws(() => branchTip(REPO, DEV_REF, fakeExec([[TIP_KEY, "null\n"]])), /unexpected branch tip/);
	assert.throws(() => branchTip(REPO, "refs/tags/v1", fakeExec([])), /invalid branch ref/);
	assert.throws(() => branchTip("bad repo", DEV_REF, fakeExec([])), /invalid repository/);
});

test("guardDecision skips only a stale re-run: tip moved on and the published revision is newer", () => {
	const ref = "ghcr.io/o/afterglow:dev";
	const decide = (exec, sha = SHA_A) => guardDecision({ imageRef: ref, sha, repository: REPO, branchRef: DEV_REF }, exec);
	const published = (rev) => [/imagetools inspect/, JSON.stringify(config(rev))];
	const tip = (sha) => [TIP_KEY, `${sha}\n`];

	// 오래된 실행의 재실행: dev 는 SHA_B 로 이동했고 :dev 도 SHA_B 에서 발행됐다.
	const stale = decide(fakeExec([published(SHA_B), tip(SHA_B), [/compare/, "behind"]]));
	assert.equal(stale.retag, false);
	assert.match(stale.reason, /stale re-run/);

	// force-push rollback: 이번 SHA_A 가 브랜치 끝이다. 발행본(SHA_B)이 ancestry 상 더 새로워도 발행한다.
	const rollback = fakeExec([published(SHA_B), tip(SHA_A)]);
	assert.equal(decide(rollback).retag, true);
	assert.equal(rollback.calls.some((call) => call.includes("/compare/")), false, "tip == sha needs no compare");

	// 브랜치 끝이 다른 SHA 여도 이번 SHA 가 발행본보다 새로우면 발행한다(동시 실행 순서 역전 포함).
	for (const status of ["ahead", "identical", "diverged"]) {
		assert.equal(decide(fakeExec([published(SHA_B), tip(SHA_C), [/compare/, status]])).retag, true, status);
	}

	const same = fakeExec([published(SHA_A)]);
	assert.equal(decide(same).retag, true);
	assert.equal(same.calls.some((call) => call.startsWith("gh ")), false);

	// 알 수 없으면 진행한다. 조회 오류는 warning 을 단다.
	const absent = decide(fakeExec([[/imagetools inspect/, commandError("ERROR: not found")]]));
	assert.deepEqual([absent.retag, Boolean(absent.warning)], [true, false]);
	const noLabel = decide(fakeExec([[/imagetools inspect/, JSON.stringify(config())]]));
	assert.deepEqual([noLabel.retag, Boolean(noLabel.warning)], [true, false]);
	const inspectError = decide(fakeExec([[/imagetools inspect/, commandError("ERROR: 401 Unauthorized")]]));
	assert.deepEqual([inspectError.retag, inspectError.warning], [true, true]);
	const tipError = decide(fakeExec([published(SHA_B), [TIP_KEY, new Error("HTTP 502")]]));
	assert.deepEqual([tipError.retag, tipError.warning], [true, true]);
	const compareError = decide(fakeExec([published(SHA_B), tip(SHA_C), [/compare/, new Error("HTTP 404")]]));
	assert.deepEqual([compareError.retag, compareError.warning], [true, true]);
});

test("CLI guard exits 3 with a notice for a stale re-run and 0 otherwise", () => {
	const ref = "ghcr.io/o/afterglow:dev";
	const stale = fakeExec([[/imagetools inspect/, JSON.stringify(config(SHA_B))], [TIP_KEY, SHA_B], [/compare/, "behind"]]);
	const out = sink();
	assert.equal(main(["guard", ref, SHA_A, REPO, DEV_REF], { exec: stale, stdout: out, stderr: sink() }), GUARD_SKIP_EXIT);
	assert.match(out.text(), /^::notice title=Stale re-run::/m);

	const rollback = fakeExec([[/imagetools inspect/, JSON.stringify(config(SHA_B))], [TIP_KEY, SHA_A]]);
	assert.equal(main(["guard", ref, SHA_A, REPO, DEV_REF], { exec: rollback, stdout: sink(), stderr: sink() }), 0);

	const fresh = fakeExec([[/imagetools inspect/, JSON.stringify(config(SHA_B))], [TIP_KEY, SHA_C], [/compare/, "ahead"]]);
	assert.equal(main(["guard", ref, SHA_A, REPO, DEV_REF], { exec: fresh, stdout: sink(), stderr: sink() }), 0);

	const warned = sink();
	const broken = fakeExec([[/imagetools inspect/, commandError("ERROR: 401 Unauthorized")]]);
	assert.equal(main(["guard", ref, SHA_A, REPO, DEV_REF], { exec: broken, stdout: warned, stderr: sink() }), 0);
	assert.match(warned.text(), /^::warning title=Stale re-run guard::/m);

	// 인자가 빠지거나 잘못되면 가드를 건너뛰지 않고 leg 를 실패시킨다(exit 2).
	for (const args of [
		[ref, "HEAD", REPO, DEV_REF],
		[ref, SHA_A, REPO],
		[ref, SHA_A, REPO, "refs/tags/v1.2.3"],
		[ref, SHA_A, "bad repo", DEV_REF],
	]) {
		assert.equal(main(["guard", ...args], { exec: fakeExec([]), stdout: sink(), stderr: sink() }), 2, args.join(" "));
	}
});

test("CLI verify prints only the digest when the per-arch image carries this revision", () => {
	const ref = "ghcr.io/o/afterglow-api:dev-amd64";
	const routes = (revision) => [
		[`docker buildx imagetools inspect ${ref}`, `Digest:    ${DIGEST}\n`],
		[/@sha256:.* --format/, JSON.stringify(config(revision))],
	];
	const out = sink();
	assert.equal(main(["verify", ref, SHA_A], { exec: fakeExec(routes(SHA_A)), stdout: out, stderr: sink() }), 0);
	assert.equal(out.text(), `${DIGEST}\n`);

	// 실패 진단은 stderr 로만 간다. stdout 은 $(...) 로 digest 를 받는 통로라 비어 있어야 한다.
	const staleOut = sink();
	const stale = sink();
	assert.equal(main(["verify", ref, SHA_A], { exec: fakeExec(routes(SHA_B)), stdout: staleOut, stderr: stale }), 1);
	assert.match(stale.text(), /^::error::.*carries revision b{40}, expected a{40}/m);
	assert.equal(staleOut.text(), "");

	const unlabeled = sink();
	assert.equal(main(["verify", ref, SHA_A], { exec: fakeExec(routes(undefined)), stdout: sink(), stderr: unlabeled }), 1);
	assert.match(unlabeled.text(), /carries revision <none>/);

	const missingOut = sink();
	const missing = sink();
	const gone = fakeExec([[/imagetools inspect/, new Error("manifest unknown")]]);
	assert.equal(main(["verify", ref, SHA_A], { exec: gone, stdout: missingOut, stderr: missing }), 1);
	assert.match(missing.text(), /not readable in the registry/);
	assert.equal(missingOut.text(), "");
});
