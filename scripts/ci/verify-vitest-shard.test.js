const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { listSuiteFiles, main, parseShard, verifyShardReport } = require("./verify-vitest-shard.js");

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

test("a real partial shard passes", () => {
	const result = verifyShardReport(report(["/a", "/b"]), 4, { index: 1, count: 2 });
	assert.equal(result.ok, true, result.errors.join("; "));
	assert.equal(result.ranFiles, 2);
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

test("failed tests, failed files and success=false fail the shard", () => {
	const shard = { index: 1, count: 2 };
	assert.equal(verifyShardReport(report(["/a"], { numFailedTests: 1 }), 4, shard).ok, false);
	assert.equal(verifyShardReport(report(["/a"], { numFailedTestSuites: 1 }), 4, shard).ok, false);
	assert.equal(verifyShardReport(report(["/a"], { success: false }), 4, shard).ok, false);
	const failedFile = report(["/a"]);
	failedFile.testResults[0].status = "failed";
	assert.match(verifyShardReport(failedFile, 4, shard).errors.join("\n"), /failed files: \/a/);
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
