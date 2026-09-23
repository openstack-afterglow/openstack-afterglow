#!/usr/bin/env node
"use strict";

// docker-build.yml `changes` job 의 이미지 빌드 대상 결정.
//
// 규칙
// - workflow_dispatch: 입력 targets 를 그대로 매핑한다(지원하지 않는 값은 exit 1).
// - dev 브랜치 push 이외(main, v* 태그, PR): 전체 빌드. diff 를 계산하지 않는다.
//   PR 은 빌드 잡 자체가 실행되지 않으므로 PR diff 도 계산하지 않는다.
// - dev push: 두 기준의 합집합.
//   1) event 기준: `git diff <github.event.before> HEAD`. before 를 depth=1 로 fetch 한다.
//      all-zero before(새 브랜치), forced push, fetch/diff 실패는 전체 빌드. 잘못된 before 와 fetch/diff 실패는
//      예상하지 못한 경우이므로 ::warning:: 을 남긴다(예: 익명 fetch 가 막히면 모든 dev push 가 전체 빌드가 된다).
//   2) 발행 revision 기준(실패한 이전 실행의 누락분 복구): target 별로 현재 발행된 :dev 이미지의
//      org.opencontainers.image.revision 을 읽는다.
//      - 이미지 없음(not found/manifest unknown) 또는 label 없음(bootstrap): event 기준만 사용한다.
//      - 레지스트리 인증·전송·rate limit·형식 오류: 그 target 을 빌드하고 ::warning:: 을 남긴다.
//        조회 실패를 부재로 취급하면 carry-over 복구가 조용히 꺼진다.
//      - HEAD 의 조상(compare ahead/identical): `git diff <rev> HEAD` 를 그 target 의 경로 규칙으로 판정.
//      - behind(발행본이 HEAD 보다 새로움 = 오래된 실행의 재실행): event 기준만 사용한다.
//        :dev 이동은 manifest 의 stale re-run 가드가 막는다.
//      - diverged, 또는 revision 을 읽은 뒤의 compare/fetch/diff 실패: 그 target 을 빌드한다(fail-safe).
// - push 의 마지막 커밋만 보는 tip-only 비교(첫 부모와 HEAD 의 diff)는 쓰지 않는다.
//
// 경로 규칙(Afterglow 배포 세트): backend/worker 는 afterglow 규칙, frontend 는 frontend 규칙 또는
// afterglow 규칙, cloud-shell 은 cloud-shell 규칙. backend/worker 가 빌드되면 frontend 도 함께 빌드한다.
// docker-build.yml 자체가 바뀌면 전체(발행 revision 기준에서는 그 target)를 빌드한다.

const fs = require("node:fs");
const { execFileSync } = require("node:child_process");
const { SHA_RE, compareStatus, readRevision } = require("./image-revision.js");

const ALL_TARGETS = ["backend", "frontend", "worker", "cloud-shell"];
const IMAGE_NAMES = {
	backend: "afterglow-api",
	frontend: "afterglow",
	worker: "afterglow-worker",
	"cloud-shell": "afterglow-cloud-shell",
};
const PATH_RULES = {
	pipeline: String.raw`^\.github/workflows/docker-build\.yml$`,
	afterglow: String.raw`^(backend/|Dockerfile$|\.dockerignore$|services/afterglow-crypto/)`,
	frontend: String.raw`^(frontend/|Dockerfile$|\.dockerignore$)`,
	cloudShell: String.raw`^(cloud-shell/|Dockerfile$|\.dockerignore$)`,
};
const PATTERNS = Object.fromEntries(Object.entries(PATH_RULES).map(([key, source]) => [key, new RegExp(source)]));
const DISPATCH_MAP = {
	backend: ["backend"],
	frontend: ["frontend"],
	worker: ["worker"],
	"cloud-shell": ["cloud-shell"],
	afterglow: ALL_TARGETS,
	all: ALL_TARGETS,
};
const DEV_REF = "refs/heads/dev";

function defaultExec(cmd, args) {
	return execFileSync(cmd, args, {
		encoding: "utf8",
		stdio: ["ignore", "pipe", "pipe"],
		timeout: 120_000,
	});
}

function ordered(targets) {
	const set = new Set(targets);
	return ALL_TARGETS.filter((target) => set.has(target));
}

function classify(files) {
	const groups = { pipeline: false, afterglow: false, frontend: false, cloudShell: false };
	for (const file of files) {
		for (const key of Object.keys(groups)) {
			if (PATTERNS[key].test(file)) groups[key] = true;
		}
	}
	return groups;
}

/** 변경 파일 목록이 요구하는 target 집합(배포 세트 결합 포함). */
function targetsForFiles(files) {
	const groups = classify(files);
	if (groups.pipeline) return [...ALL_TARGETS];
	const targets = [];
	if (groups.afterglow) targets.push("backend", "worker");
	if (groups.frontend || groups.afterglow) targets.push("frontend");
	if (groups.cloudShell) targets.push("cloud-shell");
	return ordered(targets);
}

function isZeroSha(value) {
	return /^0+$/.test(value ?? "");
}

function splitLines(output) {
	return String(output)
		.split(/\r?\n/)
		.map((line) => line.trim())
		.filter(Boolean);
}

/**
 * 순수 결정 함수.
 * @param {object} input
 * @param {string} input.eventName
 * @param {string} input.ref
 * @param {string} [input.dispatchTargets]
 * @param {string[]|null} [input.eventChanges] dev push 의 event 기준 변경 파일. null 이면 기준 없음(전체 빌드).
 * @param {string} [input.eventBasis] eventChanges 를 만든 기준 설명(로그용).
 * @param {Record<string, {kind: string, files?: string[], revision?: string, reason?: string}>} [input.published]
 *   kind: selected | absent | behind | diverged | error | diff. 항목이 없으면(미조회) event 기준만 쓴다.
 */
function decideTargets(input) {
	const reasons = [];
	const { eventName, ref } = input;

	if (eventName === "workflow_dispatch") {
		const requested = input.dispatchTargets || "all";
		const mapped = DISPATCH_MAP[requested];
		if (!mapped) throw new Error(`Unsupported dispatch target: ${requested}`);
		reasons.push(`workflow_dispatch targets=${requested}`);
		return { targets: ordered(mapped), reasons };
	}

	if (eventName !== "push" || ref !== DEV_REF) {
		reasons.push(`${eventName} on ${ref}: full Afterglow build`);
		return { targets: [...ALL_TARGETS], reasons };
	}

	if (!Array.isArray(input.eventChanges)) {
		reasons.push(`dev push without a usable event basis (${input.eventBasis || "unknown"}): full build`);
		return { targets: [...ALL_TARGETS], reasons };
	}

	const selected = new Set(targetsForFiles(input.eventChanges));
	reasons.push(
		`event basis ${input.eventBasis || "before..HEAD"}: ${input.eventChanges.length} files -> [${ordered(selected).join(", ")}]`,
	);

	const published = input.published || {};
	for (const target of ALL_TARGETS) {
		const entry = published[target];
		if (entry?.kind === "selected") {
			reasons.push(`${target}: selected by the event basis`);
			continue;
		}
		if (!entry || entry.kind === "absent") {
			reasons.push(`${target}: no published revision (${entry?.reason || "not inspected"}); event basis only`);
			continue;
		}
		if (entry.kind === "behind") {
			reasons.push(`${target}: published ${entry.revision} is newer than HEAD (stale re-run); event basis only`);
			continue;
		}
		if (entry.kind === "diverged") {
			selected.add(target);
			reasons.push(`${target}: published ${entry.revision} diverged from HEAD; building`);
			continue;
		}
		if (entry.kind === "diff" && Array.isArray(entry.files)) {
			if (targetsForFiles(entry.files).includes(target)) {
				selected.add(target);
				reasons.push(`${target}: changes since published ${entry.revision}; building`);
			} else {
				reasons.push(`${target}: published ${entry.revision} is current for its paths`);
			}
			continue;
		}
		selected.add(target);
		reasons.push(`${target}: published revision check failed (${entry.reason || entry.kind}); building`);
	}

	// Backend/worker 와 frontend 는 같은 dev 배포 세트로 갱신한다.
	if (selected.has("backend") || selected.has("worker")) selected.add("frontend");
	return { targets: ordered(selected), reasons };
}

/**
 * push 의 event 기준 변경 파일(`before..HEAD`). 기준을 만들 수 없으면 files=null.
 * unexpected=true 는 예상하지 못한 기준 실패(잘못된 before SHA, fetch/diff 실패)다. 호출자는 전체 대상으로
 * fail-safe 하되 비용 변화가 조용히 지나가지 않게 ::warning:: 을 남긴다. 새 ref(zero SHA)·forced push 는 예상된 경우다.
 */
function collectEventChanges({ eventName, before, forced, sha }, exec = defaultExec) {
	const head = SHA_RE.test(sha ?? "") ? sha : "HEAD";
	if (eventName !== "push") return { files: null, basis: `${eventName} has no push basis`, unexpected: false };
	if (!before || isZeroSha(before)) return { files: null, basis: "all-zero before (new ref)", unexpected: false };
	if (!SHA_RE.test(before)) return { files: null, basis: `invalid before SHA ${JSON.stringify(before)}`, unexpected: true };
	if (String(forced) === "true") return { files: null, basis: "forced push", unexpected: false };
	try {
		exec("git", ["fetch", "--no-tags", "--depth=1", "origin", before]);
	} catch (error) {
		return { files: null, basis: `fetch of before ${before} failed: ${error.message.split("\n")[0]}`, unexpected: true };
	}
	try {
		return {
			files: splitLines(exec("git", ["diff", "--name-only", before, head])),
			basis: `${before}..${head}`,
			unexpected: false,
		};
	} catch (error) {
		return { files: null, basis: `diff ${before}..${head} failed: ${error.message.split("\n")[0]}`, unexpected: true };
	}
}

/** target 하나의 발행 revision 기준. 조회 오류는 부재가 아니라 error(빌드)다. */
function collectPublished({ target, imageRef, sha, repository }, exec = defaultExec) {
	const published = readRevision(imageRef, exec);
	if (published.kind === "absent") return { kind: "absent", reason: published.reason };
	if (published.kind !== "present") return { kind: "error", reason: published.reason };
	const revision = published.revision;
	if (revision === sha) return { kind: "diff", revision, files: [] };
	let status;
	try {
		status = compareStatus(repository, revision, sha, exec);
	} catch (error) {
		return { kind: "error", revision, reason: `compare failed: ${error.message.split("\n")[0]}` };
	}
	if (status === "behind") return { kind: "behind", revision };
	if (status === "diverged") return { kind: "diverged", revision };
	// ahead | identical: 발행 revision 이 HEAD 의 조상이다. 두 tree 비교에는 이력이 필요 없다.
	try {
		exec("git", ["fetch", "--no-tags", "--depth=1", "origin", revision]);
		return { kind: "diff", revision, files: splitLines(exec("git", ["diff", "--name-only", revision, sha])) };
	} catch (error) {
		return { kind: "error", revision, reason: `${target} fetch/diff failed: ${error.message.split("\n")[0]}` };
	}
}

function collectAndDecide(env, exec = defaultExec) {
	const eventName = env.GITHUB_EVENT_NAME || "";
	const ref = env.EFFECTIVE_REF || env.GITHUB_REF || "";
	const sha = env.GITHUB_SHA || "";
	const input = { eventName, ref, dispatchTargets: env.DISPATCH_TARGETS };

	const devPush = eventName === "push" && ref === DEV_REF;
	// event diff 는 dev push(선택 빌드)에서만 계산한다. main/태그/PR 은 전체, dispatch 는 입력 매핑이다.
	if (devPush) {
		const event = collectEventChanges({ eventName, before: env.EVENT_BEFORE, forced: env.EVENT_FORCED, sha }, exec);
		input.eventChanges = event.files;
		input.eventBasis = event.basis;
		input.eventBasisUnexpected = event.unexpected === true;
	}

	// 발행 revision 은 dev push 에서만, event 기준이 있을 때만 읽는다(PR 에서는 레지스트리에 접근하지 않는다).
	if (devPush && Array.isArray(input.eventChanges)) {
		const registry = env.REGISTRY || "ghcr.io";
		const owner = env.IMAGE_OWNER || "";
		const repository = env.GITHUB_REPOSITORY || "";
		const alreadySelected = new Set(targetsForFiles(input.eventChanges));
		input.published = {};
		for (const target of ALL_TARGETS) {
			const imageRef = `${registry}/${owner}/${IMAGE_NAMES[target]}:dev`;
			if (alreadySelected.has(target)) {
				input.published[target] = { kind: "selected" };
			} else if (!owner || !SHA_RE.test(sha)) {
				input.published[target] = { kind: "error", reason: "missing IMAGE_OWNER or GITHUB_SHA" };
			} else {
				input.published[target] = collectPublished({ target, imageRef, sha, repository }, exec);
			}
		}
	}

	return { ...decideTargets(input), input, warnings: collectWarnings(env, input) };
}

/** 조용히 넘어가면 안 되는 상태를 ::warning:: annotation 문구로 모은다. */
function collectWarnings(env, input) {
	const warnings = [];
	if (input.eventBasisUnexpected === true && !Array.isArray(input.eventChanges)) {
		warnings.push(`Dev push event basis is unavailable (${input.eventBasis}); building every target`);
	}
	if (env.REGISTRY_LOGIN_OUTCOME === "failure") {
		warnings.push(
			"Registry login failed; published :dev revisions may be unreadable, so affected targets are built instead of carried over",
		);
	}
	for (const [target, entry] of Object.entries(input.published || {})) {
		if (entry?.kind === "error") warnings.push(`${target}: published revision check failed (${entry.reason}); building ${target}`);
	}
	return warnings;
}

function main(env = process.env, { exec = defaultExec, stdout = process.stdout } = {}) {
	let result;
	try {
		result = collectAndDecide(env, exec);
	} catch (error) {
		stdout.write(`::error::${error.message}\n`);
		return 1;
	}
	const targets = result.targets;
	const standard = targets.filter((target) => target !== "cloud-shell");
	for (const warning of result.warnings) stdout.write(`::warning title=Image target detection::${warning}\n`);
	for (const reason of result.reasons) stdout.write(`${reason}\n`);
	if (Array.isArray(result.input.eventChanges)) {
		stdout.write(`changed files (${result.input.eventChanges.length}):\n`);
		for (const file of result.input.eventChanges.slice(0, 200)) stdout.write(`  ${file}\n`);
	}
	const lines = [
		`targets=${JSON.stringify(targets)}`,
		`standard_targets=${JSON.stringify(standard)}`,
		`cloud_shell=${targets.includes("cloud-shell")}`,
	];
	stdout.write(`${lines.join("\n")}\n`);
	if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT, `${lines.join("\n")}\n`);
	return 0;
}

module.exports = {
	ALL_TARGETS,
	IMAGE_NAMES,
	PATH_RULES,
	classify,
	collectAndDecide,
	collectEventChanges,
	collectPublished,
	decideTargets,
	main,
	targetsForFiles,
};

if (require.main === module) {
	process.exitCode = main();
}
