const assert = require("node:assert/strict");
const test = require("node:test");

const {
	GUARD_SKIP_EXIT,
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
const DIGEST = `sha256:${"c".repeat(64)}`;
const REPO = "openstack-afterglow/openstack-afterglow";

function config(revision) {
	const labels = revision === undefined ? {} : { "org.opencontainers.image.revision": revision };
	return { architecture: "amd64", os: "linux", config: { Labels: labels } };
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

test("parseRevisionLabel returns null for missing or malformed labels", () => {
	assert.equal(parseRevisionLabel(""), null);
	assert.equal(parseRevisionLabel("null"), null);
	assert.equal(parseRevisionLabel(JSON.stringify(config())), null);
	assert.equal(parseRevisionLabel(JSON.stringify({ architecture: "amd64", config: {} })), null);
	assert.equal(parseRevisionLabel(JSON.stringify(config("not-a-sha"))), null);
	assert.equal(parseRevisionLabel(JSON.stringify(config("$(touch /tmp/x)"))), null);
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

test("readRevision treats inspect failures as unknown", () => {
	const exec = fakeExec([[/imagetools inspect/, new Error("manifest unknown")]]);
	assert.equal(readRevision("ghcr.io/o/afterglow:dev", exec), null);
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

test("guardDecision skips only when the published revision is newer (compare says behind)", () => {
	const ref = "ghcr.io/o/afterglow:dev";
	const published = (rev) => [/imagetools inspect/, JSON.stringify(config(rev))];

	const behind = fakeExec([published(SHA_B), [/compare/, "behind"]]);
	assert.equal(guardDecision({ imageRef: ref, sha: SHA_A, repository: REPO }, behind).retag, false);

	for (const status of ["ahead", "identical", "diverged"]) {
		const exec = fakeExec([published(SHA_B), [/compare/, status]]);
		assert.equal(guardDecision({ imageRef: ref, sha: SHA_A, repository: REPO }, exec).retag, true, status);
	}

	const same = fakeExec([published(SHA_A)]);
	assert.equal(guardDecision({ imageRef: ref, sha: SHA_A, repository: REPO }, same).retag, true);
	assert.equal(same.calls.some((call) => call.startsWith("gh ")), false);

	const unknown = fakeExec([[/imagetools inspect/, new Error("not found")]]);
	assert.equal(guardDecision({ imageRef: ref, sha: SHA_A, repository: REPO }, unknown).retag, true);

	const noLabel = fakeExec([[/imagetools inspect/, JSON.stringify(config())]]);
	assert.equal(guardDecision({ imageRef: ref, sha: SHA_A, repository: REPO }, noLabel).retag, true);

	const compareFails = fakeExec([published(SHA_B), [/compare/, new Error("HTTP 404")]]);
	assert.equal(guardDecision({ imageRef: ref, sha: SHA_A, repository: REPO }, compareFails).retag, true);
});

test("CLI guard exits 3 with a notice for a stale re-run and 0 otherwise", () => {
	const ref = "ghcr.io/o/afterglow:dev";
	const stale = fakeExec([[/imagetools inspect/, JSON.stringify(config(SHA_B))], [/compare/, "behind"]]);
	const out = sink();
	assert.equal(main(["guard", ref, SHA_A, REPO], { exec: stale, stdout: out, stderr: sink() }), GUARD_SKIP_EXIT);
	assert.match(out.text(), /^::notice title=Stale re-run::/m);

	const fresh = fakeExec([[/imagetools inspect/, JSON.stringify(config(SHA_B))], [/compare/, "ahead"]]);
	assert.equal(main(["guard", ref, SHA_A, REPO], { exec: fresh, stdout: sink(), stderr: sink() }), 0);
	assert.equal(main(["guard", ref, "HEAD", REPO], { exec: fresh, stdout: sink(), stderr: sink() }), 2);
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
