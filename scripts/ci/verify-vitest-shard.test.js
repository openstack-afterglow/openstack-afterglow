const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { expectedShardSize, listSuiteFiles, main, parseShard, verifyShardReport } = require("./verify-vitest-shard.js");

function report(names, overrides = {}) {
	return {
		numTotalTests: names.length,
		numPassedTests: names.length,
		numFailedTests: 0,
		numFailedTestSuites: 0,
		success: true,
		testResults: names.map((name) => ({ name, status: "passed" })),
		...overrides,
	};
}

function fixture() {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "vitest-shard-"));
	const files = [
		"src/a.test.ts",
		"src/lib/b.spec.js",
		"src/lib/deep/c.test.js",
		"src/routes/d.spec.ts",
		"src/lib/not-a-test.ts",
		"src/lib/e.test.svelte",
		"src/.hidden/f.test.ts",
		"src/node_modules/g.test.ts",
		"tests/outside.test.ts",
	];
	for (const file of files) {
		fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true });
		fs.writeFileSync(path.join(root, file), "");
	}
	return root;
}

test("listSuiteFiles matches the vitest include src/**/*.{test,spec}.{js,ts}", () => {
	const root = fixture();
	try {
		const files = listSuiteFiles(root).map((file) => path.relative(root, file).split(path.sep).join("/"));
		assert.deepEqual(files, ["src/a.test.ts", "src/lib/b.spec.js", "src/lib/deep/c.test.js", "src/routes/d.spec.ts"]);
	} finally {
		fs.rmSync(root, { recursive: true, force: true });
	}
});

test("parseShard accepts index/count with count >= 2", () => {
	assert.deepEqual(parseShard("1/2"), { index: 1, count: 2 });
	assert.deepEqual(parseShard("2/2"), { index: 2, count: 2 });
	assert.throws(() => parseShard("1/1"), /invalid shard/);
	assert.throws(() => parseShard("3/2"), /invalid shard/);
	assert.throws(() => parseShard("0/2"), /invalid shard/);
	assert.throws(() => parseShard("1"), /index/);
});

test("expectedShardSize matches the vitest 4 distributed shard range", () => {
	// 로컬 실측: 247 파일 → 124 / 123.
	assert.equal(expectedShardSize(247, { index: 1, count: 2 }), 124);
	assert.equal(expectedShardSize(247, { index: 2, count: 2 }), 123);
	assert.equal(expectedShardSize(4, { index: 1, count: 2 }), 2);
	// count > 2 에서는 ceil 분할(3,3,3,1)이 아니라 앞쪽 샤드에 나머지를 하나씩 준다(3,3,2,2).
	assert.deepEqual([1, 2, 3, 4].map((index) => expectedShardSize(10, { index, count: 4 })), [3, 3, 2, 2]);
	for (const [total, count] of [[247, 2], [247, 3], [10, 4], [5, 5], [3, 4]]) {
		const sizes = Array.from({ length: count }, (_, i) => expectedShardSize(total, { index: i + 1, count }));
		assert.equal(sizes.reduce((sum, size) => sum + size, 0), total, `${total}/${count}`);
	}
});

test("a real partial shard passes", () => {
	const result = verifyShardReport(report(["/a", "/b"]), 4, { index: 1, count: 2 });
	assert.equal(result.ok, true, result.errors.join("; "));
	assert.equal(result.ranFiles, 2);
	assert.equal(verifyShardReport(report(["/a", "/b"]), 3, { index: 1, count: 2 }).ok, true);
	assert.equal(verifyShardReport(report(["/c"]), 3, { index: 2, count: 2 }).ok, true);
});

test("a shard whose size differs from the vitest split fails", () => {
	// 파일 walk 가 vitest 보다 많이 세면(예: vitest exclude 추가) 전체 스위트(vitest 기준 4개)를 돈 샤드도
	// 예전 `0 < ran < suite(5)` 검사를 통과했다. 정확한 분할 크기(3)와 비교하면 실패한다.
	const wholeSuite = verifyShardReport(report(["/a", "/b", "/c", "/d"]), 5, { index: 1, count: 2 });
	assert.equal(wholeSuite.ok, false);
	assert.match(wholeSuite.errors.join("\n"), /ran 4 files but vitest assigns 3 of 5/);
	const tooFew = verifyShardReport(report(["/a"]), 4, { index: 1, count: 2 });
	assert.equal(tooFew.ok, false);
	assert.match(tooFew.errors.join("\n"), /ran 1 files but vitest assigns 2 of 4/);
});

test("a shard that silently ran the whole suite fails", () => {
	const result = verifyShardReport(report(["/a", "/b", "/c", "/d"]), 4, { index: 1, count: 2 });
	assert.equal(result.ok, false);
	assert.match(result.errors.join("\n"), /--shard was not applied/);
});

test("an empty shard, a missing report shape and an unknown suite size fail", () => {
	assert.match(verifyShardReport(report([]), 4, { index: 2, count: 2 }).errors.join("\n"), /ran no test files/);
	assert.equal(verifyShardReport({}, 4, { index: 1, count: 2 }).ok, false);
	assert.match(verifyShardReport(report(["/a"]), 0, { index: 1, count: 2 }).errors.join("\n"), /full suite file count is 0/);
});

test("failed tests, failed files and success=false each fail an otherwise valid shard", () => {
	// 각 경우는 크기 검사를 통과하는 보고서(2 of 4, shard 1/2)에서 시작하므로 해당 조건 하나만 실패 원인이다.
	const shard = { index: 1, count: 2 };
	const valid = () => report(["/a", "/b"]);
	assert.deepEqual(verifyShardReport(valid(), 4, shard).errors, [], "the base report is a valid shard");

	const cases = [
		["failed tests", { ...valid(), numFailedTests: 1 }, "1 failed tests"],
		["failed suites", { ...valid(), numFailedTestSuites: 1 }, "1 failed suites"],
		["success=false", { ...valid(), success: false }, "vitest reported success=false"],
		["success missing", { ...valid(), success: undefined }, "vitest reported success=false"],
	];
	const failedFile = valid();
	failedFile.testResults[1].status = "failed";
	cases.push(["failed file", failedFile, "failed files: /b"]);

	for (const [label, input, message] of cases) {
		const result = verifyShardReport(input, 4, shard);
		assert.equal(result.ok, false, label);
		assert.deepEqual(result.errors, [message], label);
	}
});

test("main reads the report, counts the suite and emits annotations on failure", () => {
	const root = fixture();
	try {
		const reportPath = path.join(root, "report.json");
		const lines = [];
		const stdout = { write: (line) => lines.push(line) };

		fs.writeFileSync(reportPath, JSON.stringify(report(["/a", "/b"])));
		assert.equal(main(["--report", reportPath, "--shard", "1/2", "--root", root], { stdout }), 0);
		assert.match(lines.join(""), /shard 1\/2: 2 of 4 files/);

		lines.length = 0;
		fs.writeFileSync(reportPath, JSON.stringify(report(["/a", "/b", "/c", "/d"])));
		assert.equal(main(["--report", reportPath, "--shard", "2/2", "--root", root], { stdout }), 1);
		assert.match(lines.join(""), /::error title=Vitest shard 2\/2::/);

		lines.length = 0;
		assert.equal(main(["--report", path.join(root, "missing.json"), "--shard", "1/2"], { stdout }), 1);
		assert.match(lines.join(""), /could not start/);
	} finally {
		fs.rmSync(root, { recursive: true, force: true });
	}
});
