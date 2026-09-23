#!/usr/bin/env node
"use strict";

// helm-release.yml `check-changes` 잡의 chart 발행 판단(CLAUDE.md "CI 파이프라인 성능 규정" 8번).
//
// 규칙
// - v* 태그 push, workflow_dispatch: 항상 발행한다.
// - main push: `github.event.before..github.sha` 에 `helm/afterglow/` 변경이 있으면 발행한다.
//   before 는 detect-build-targets.js 의 collectEventChanges 로 depth=1 fetch 뒤 비교한다.
//   all-zero before(새 ref), forced push, 잘못된 before, fetch/diff 실패는 발행한다(fail-safe).
//   잘못된 before 와 fetch/diff 실패는 예상하지 못한 경우이므로 ::warning:: 을 남긴다.
// - 그 밖의 이벤트, 판단 중 예외: 발행한다(fail-safe).
// - push 의 마지막 커밋만 보는 tip-only 비교(첫 부모와 HEAD 의 diff)는 쓰지 않는다. fast-forward 로 여러 커밋이
//   들어온 main push 에서 앞 커밋의 chart 변경을 놓치기 때문이다.
//
// main() 은 항상 exit 0 이고 publish 를 GITHUB_OUTPUT 에 정확히 한 번, 마지막에 쓴다.

const fs = require("node:fs");
const { collectEventChanges } = require("./detect-build-targets.js");

const CHART_PATH = /^helm\/afterglow\//;

/**
 * @returns {{ publish: boolean, reasons: string[], warnings: string[], files?: string[] }}
 */
function decidePublish(env, exec) {
	const eventName = env.GITHUB_EVENT_NAME || "";
	const ref = env.GITHUB_REF || "";
	if (eventName === "workflow_dispatch") return { publish: true, reasons: ["workflow_dispatch: publish"], warnings: [] };
	if (env.GITHUB_REF_TYPE === "tag" || ref.startsWith("refs/tags/")) {
		return { publish: true, reasons: [`tag ${ref}: publish`], warnings: [] };
	}
	if (eventName !== "push") return { publish: true, reasons: [`${eventName || "unknown event"}: publish (fail-safe)`], warnings: [] };

	// exec 가 undefined 이면 collectEventChanges 의 기본 execFileSync 를 쓴다.
	const event = collectEventChanges({ eventName, before: env.EVENT_BEFORE, forced: env.EVENT_FORCED, sha: env.GITHUB_SHA }, exec);
	if (!Array.isArray(event.files)) {
		const warnings = event.unexpected === true ? [`Push basis is unavailable (${event.basis}); publishing the chart`] : [];
		return { publish: true, reasons: [`push without a usable basis (${event.basis}): publish`], warnings };
	}
	const chartFiles = event.files.filter((file) => CHART_PATH.test(file));
	if (chartFiles.length > 0) {
		return { publish: true, reasons: [`${event.basis}: ${chartFiles.length} helm/afterglow/ files changed: publish`], warnings: [], files: chartFiles };
	}
	return { publish: false, reasons: [`${event.basis}: no helm/afterglow/ changes in ${event.files.length} files; chart publish skipped`], warnings: [] };
}

function main(env = process.env, { exec, stdout = process.stdout } = {}) {
	let result;
	try {
		result = decidePublish(env, exec);
	} catch (error) {
		const message = error && typeof error.message === "string" ? error.message.split("\n")[0] : String(error);
		result = { publish: true, reasons: [`decision failed: publish (fail-safe)`], warnings: [`Chart publish decision failed (${message}); publishing`] };
	}
	for (const warning of result.warnings) stdout.write(`::warning title=Helm chart publish::${warning}\n`);
	for (const reason of result.reasons) stdout.write(`${reason}\n`);
	for (const file of (result.files || []).slice(0, 200)) stdout.write(`  ${file}\n`);
	const line = `publish=${result.publish === true}\n`;
	stdout.write(line);
	if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT, line);
	return 0;
}

module.exports = { CHART_PATH, decidePublish, main };

if (require.main === module) {
	process.exitCode = main();
}
