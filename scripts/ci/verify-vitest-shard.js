#!/usr/bin/env node
"use strict";

// frontend vitest 샤드 검증.
//
// `npm run test:unit:frontend -- --shard=1/2` 는 내부 npm 이 인자를 삼켜 각 샤드가 전체 스위트를 조용히
// 실행한다. CI 는 vitest 를 직접 호출하고 JSON reporter 결과를 이 스크립트로 검증한다.
// - 이 샤드가 실행한 파일 수 > 0
// - 이 샤드가 실행한 파일 수 < 전체 스위트 파일 수(vitest include `src/**/*.{test,spec}.{js,ts}`)
// - 실패한 테스트·파일 없음
//
// usage: node scripts/ci/verify-vitest-shard.js --report <vitest-json> --shard <index>/<count> [--root <frontend dir>]

const fs = require("node:fs");
const path = require("node:path");

const TEST_FILE_RE = /\.(test|spec)\.(js|ts)$/;
const SKIPPED_DIRS = new Set(["node_modules", ".git"]);

/** vitest include `src/**\/*.{test,spec}.{js,ts}` 와 같은 규칙으로 전체 테스트 파일을 센다. */
function listSuiteFiles(root) {
	const srcDir = path.join(root, "src");
	const files = [];
	const walk = (dir) => {
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			if (entry.name.startsWith(".")) continue;
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) {
				if (!SKIPPED_DIRS.has(entry.name)) walk(full);
			} else if (entry.isFile() && TEST_FILE_RE.test(entry.name)) {
				files.push(full);
			}
		}
	};
	walk(srcDir);
	return files.sort();
}

function parseShard(value) {
	const match = /^(\d+)\/(\d+)$/.exec(String(value ?? ""));
	if (!match) throw new Error(`--shard must be <index>/<count>, got ${JSON.stringify(value)}`);
	const index = Number(match[1]);
	const count = Number(match[2]);
	if (count < 2 || index < 1 || index > count) throw new Error(`invalid shard ${value}`);
	return { index, count };
}

/**
 * @param {object} report vitest JSON reporter 결과
 * @param {number} suiteFileCount 전체 스위트 파일 수
 * @returns {{ ok: boolean, errors: string[], ranFiles: number, summary: string }}
 */
function verifyShardReport(report, suiteFileCount, shard) {
	const errors = [];
	const results = Array.isArray(report?.testResults) ? report.testResults : null;
	if (!results) {
		return { ok: false, errors: ["report has no testResults array"], ranFiles: 0, summary: "" };
	}
	const ranFiles = new Set(results.map((result) => result?.name).filter(Boolean)).size;
	const label = shard ? `${shard.index}/${shard.count}` : "?";

	if (!(suiteFileCount > 0)) errors.push(`full suite file count is ${suiteFileCount}; cannot verify sharding`);
	if (ranFiles === 0) errors.push(`shard ${label} ran no test files`);
	if (suiteFileCount > 0 && ranFiles >= suiteFileCount) {
		errors.push(
			`shard ${label} ran ${ranFiles} of ${suiteFileCount} files; --shard was not applied (the whole suite ran)`,
		);
	}
	const failedFiles = results.filter((result) => result?.status === "failed").map((result) => result.name);
	if (failedFiles.length) errors.push(`failed files: ${failedFiles.join(", ")}`);
	if (Number(report.numFailedTests) > 0) errors.push(`${report.numFailedTests} failed tests`);
	if (Number(report.numFailedTestSuites) > 0) errors.push(`${report.numFailedTestSuites} failed suites`);
	if (report.success !== true) errors.push("vitest reported success=false");

	const summary = `shard ${label}: ${ranFiles} of ${suiteFileCount} files, ${report.numTotalTests ?? "?"} tests (${report.numPassedTests ?? "?"} passed)`;
	return { ok: errors.length === 0, errors, ranFiles, summary };
}

function parseArgs(argv) {
	const args = {};
	for (let i = 0; i < argv.length; i += 1) {
		const key = argv[i];
		if (!key.startsWith("--")) throw new Error(`unexpected argument ${key}`);
		args[key.slice(2)] = argv[i + 1];
		i += 1;
	}
	return args;
}

function main(argv, { stdout = process.stdout, cwd = process.cwd() } = {}) {
	let args;
	let shard;
	let report;
	try {
		args = parseArgs(argv);
		shard = parseShard(args.shard);
		if (!args.report) throw new Error("--report is required");
		report = JSON.parse(fs.readFileSync(path.resolve(cwd, args.report), "utf8"));
	} catch (error) {
		stdout.write(`::error::vitest shard verification could not start: ${error.message}\n`);
		return 1;
	}
	const root = path.resolve(cwd, args.root || ".");
	const suiteFiles = listSuiteFiles(root);
	const result = verifyShardReport(report, suiteFiles.length, shard);
	stdout.write(`${result.summary}\n`);
	if (!result.ok) {
		for (const error of result.errors) stdout.write(`::error title=Vitest shard ${shard.index}/${shard.count}::${error}\n`);
		return 1;
	}
	return 0;
}

module.exports = { listSuiteFiles, main, parseShard, verifyShardReport };

if (require.main === module) {
	process.exitCode = main(process.argv.slice(2));
}
