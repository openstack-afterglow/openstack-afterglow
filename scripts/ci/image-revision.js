#!/usr/bin/env node
"use strict";

// 발행된 이미지의 revision(OCI label org.opencontainers.image.revision) 을 읽고,
// manifest 발행 전 per-arch 이미지 검증과 stale re-run 가드를 수행한다.
//
// docker-build.yml 에서 사용한다.
//   verify <image-ref> <sha>           : ref 의 digest 를 얻고 그 digest 의 revision 이 sha 인지 검증.
//                                        성공 시 stdout 에 digest 만 출력, 불일치/조회 실패 시 stderr 에
//                                        ::error:: 를 쓰고 exit 1.
//   guard  <image-ref> <sha> <repo> <tracked-ref>
//                                      : tracked-ref 는 image-ref 태그가 추적하는 브랜치(refs/heads/...)이다
//                                        (:dev→refs/heads/dev, :nightly→refs/heads/main). 실행 ref 가 아니다.
//                                        sha 가 그 브랜치의 끝이 아니고, 현재 발행된 ref 의 revision 이 sha 보다
//                                        앞서 있으면(compare=behind) exit 3(retag 건너뜀). sha 가 브랜치 끝이면
//                                        (정상 push, force-push rollback) exit 0(발행). tip·revision·compare 중
//                                        하나라도 알 수 없으면 exit 0(진행).
//
// 모든 외부 명령은 execFileSync 인자 배열로 실행한다(쉘 보간 없음).

const { execFileSync } = require("node:child_process");

const REVISION_LABEL = "org.opencontainers.image.revision";
const SHA_RE = /^[0-9a-f]{40}$/;
const DIGEST_RE = /^sha256:[0-9a-f]{64}$/;
const REPO_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const BRANCH_REF_RE = /^refs\/heads\/([A-Za-z0-9._/-]+)$/;
const GUARD_SKIP_EXIT = 3;
// 이미지·태그가 없다는 레지스트리 응답. 인증·권한 오류 문구가 함께 있으면 부재로 보지 않는다.
const ABSENT_RE = /\b(not found|manifest unknown|name unknown)\b/i;
const AUTH_RE = /unauthori[sz]ed|denied|forbidden|authenticat|\b40[13]\b/i;

function defaultExec(cmd, args) {
	return execFileSync(cmd, args, {
		encoding: "utf8",
		stdio: ["ignore", "pipe", "pipe"],
		timeout: 120_000,
	});
}

function labelsOf(config) {
	if (!config || typeof config !== "object") return null;
	const inner = config.config;
	if (!inner || typeof inner !== "object") return null;
	const labels = inner.Labels;
	return labels && typeof labels === "object" ? labels : {};
}

/**
 * `docker buildx imagetools inspect <ref> --format '{{json .Image}}'` 출력에서 revision label 을 읽는다.
 * 단일 플랫폼이면 image config 객체, 다중 플랫폼이면 platform → config map 이다.
 * label 이 없으면 null. label 형식이 SHA 가 아니거나 플랫폼마다 revision 이 다르면 예외.
 */
function parseRevisionLabel(inspectOutput) {
	const text = String(inspectOutput ?? "").trim();
	if (!text || text === "null") return null;
	const parsed = JSON.parse(text);
	if (!parsed || typeof parsed !== "object") return null;

	let configs;
	const single = labelsOf(parsed);
	if (single !== null) {
		configs = [parsed];
	} else {
		configs = Object.values(parsed).filter((value) => labelsOf(value) !== null);
	}

	const revisions = new Set();
	for (const config of configs) {
		const value = labelsOf(config)[REVISION_LABEL];
		if (typeof value === "string" && value.trim()) revisions.add(value.trim().toLowerCase());
	}
	if (revisions.size === 0) return null;
	if (revisions.size > 1) {
		throw new Error(`platform images disagree on ${REVISION_LABEL}: ${[...revisions].join(", ")}`);
	}
	const [revision] = revisions;
	if (!SHA_RE.test(revision)) throw new Error(`malformed ${REVISION_LABEL} label: ${JSON.stringify(revision.slice(0, 80))}`);
	return revision;
}

/** `docker buildx imagetools inspect <ref>` 기본 출력의 `Digest:` 줄에서 manifest digest 를 읽는다. */
function parseDigest(inspectOutput) {
	for (const line of String(inspectOutput ?? "").split(/\r?\n/)) {
		const match = /^Digest:\s+(\S+)\s*$/.exec(line);
		if (match) {
			if (!DIGEST_RE.test(match[1])) throw new Error(`malformed digest: ${match[1]}`);
			return match[1];
		}
	}
	throw new Error("no Digest line in imagetools inspect output");
}

/** `registry/owner/name:tag` 또는 `registry/owner/name@sha256:...` 에서 repository 부분만 남긴다. */
function repositoryOf(imageRef) {
	const at = imageRef.indexOf("@");
	const withoutDigest = at >= 0 ? imageRef.slice(0, at) : imageRef;
	const lastSlash = withoutDigest.lastIndexOf("/");
	const lastColon = withoutDigest.lastIndexOf(":");
	return lastColon > lastSlash ? withoutDigest.slice(0, lastColon) : withoutDigest;
}

function firstLine(text) {
	return (
		String(text ?? "")
			.split(/\r?\n/)
			.map((line) => line.trim())
			.find(Boolean) || "<no output>"
	);
}

/** execFileSync 오류의 message 와 stderr 를 합친 진단 문자열. */
function errorText(error) {
	return `${error?.message ?? error}\n${error?.stderr ?? ""}`;
}

/**
 * 발행된 ref 의 revision 조회 결과.
 * - `{kind: "present", revision}`: label 이 이번 조회로 확인됐다.
 * - `{kind: "absent", reason}`: 이미지가 없거나(not found/manifest unknown) label 이 없다(bootstrap).
 * - `{kind: "error", reason}`: 인증·전송·rate limit·출력 형식 오류 등. 호출자는 "모름"으로 다뤄야 하며
 *   조용히 부재로 취급하지 않는다(target 감지는 그 target 을 빌드한다).
 */
function readRevision(imageRef, exec = defaultExec) {
	let output;
	try {
		output = exec("docker", ["buildx", "imagetools", "inspect", imageRef, "--format", "{{json .Image}}"]);
	} catch (error) {
		const text = errorText(error);
		if (ABSENT_RE.test(text) && !AUTH_RE.test(text)) {
			return { kind: "absent", reason: `${imageRef} is not published` };
		}
		const detail = error?.stderr ? firstLine(error.stderr) : firstLine(error?.message ?? error);
		return { kind: "error", reason: `inspect ${imageRef} failed: ${detail}` };
	}
	let revision;
	try {
		revision = parseRevisionLabel(output);
	} catch (error) {
		return { kind: "error", reason: `${imageRef}: ${firstLine(error.message)}` };
	}
	if (!revision) return { kind: "absent", reason: `${imageRef} has no ${REVISION_LABEL} label` };
	return { kind: "present", revision };
}

/** ref 의 digest 와 그 digest 에 고정된 revision. 실패 시 예외. */
function inspectPinned(imageRef, exec = defaultExec) {
	const digest = parseDigest(exec("docker", ["buildx", "imagetools", "inspect", imageRef]));
	const pinned = `${repositoryOf(imageRef)}@${digest}`;
	const revision = parseRevisionLabel(
		exec("docker", ["buildx", "imagetools", "inspect", pinned, "--format", "{{json .Image}}"]),
	);
	return { digest, pinned, revision };
}

/** GitHub compare API 의 status(ahead/behind/identical/diverged). 실패 시 예외. */
function compareStatus(repository, base, head, exec = defaultExec) {
	if (!SHA_RE.test(base) || !SHA_RE.test(head)) throw new Error("compare requires full commit SHAs");
	if (!REPO_RE.test(repository ?? "")) throw new Error(`invalid repository: ${repository}`);
	const status = String(exec("gh", ["api", `repos/${repository}/compare/${base}...${head}`, "--jq", ".status"])).trim();
	if (!["ahead", "behind", "identical", "diverged"].includes(status)) {
		throw new Error(`unexpected compare status: ${status || "<empty>"}`);
	}
	return status;
}

/** `refs/heads/<name>` 에서 브랜치 이름. 형식이 다르면 null. */
function branchNameOf(branchRef) {
	const match = BRANCH_REF_RE.exec(String(branchRef ?? ""));
	if (!match || match[1].split("/").some((part) => part === "" || part === "." || part === "..")) return null;
	return match[1];
}

/** 브랜치의 현재 끝 commit SHA(GitHub git refs API). 실패 시 예외. */
function branchTip(repository, branchRef, exec = defaultExec) {
	const branch = branchNameOf(branchRef);
	if (!branch) throw new Error(`invalid branch ref: ${branchRef}`);
	if (!REPO_RE.test(repository ?? "")) throw new Error(`invalid repository: ${repository}`);
	const tip = String(exec("gh", ["api", `repos/${repository}/git/ref/heads/${branch}`, "--jq", ".object.sha"]))
		.trim()
		.toLowerCase();
	if (!SHA_RE.test(tip)) throw new Error(`unexpected branch tip: ${tip || "<empty>"}`);
	return tip;
}

/**
 * stale re-run 가드 결정. 아래를 모두 확인했을 때만 retag 를 건너뛴다.
 * 1. 현재 발행된 revision 을 읽었고 sha 와 다르다.
 * 2. sha 가 더 이상 브랜치 끝이 아니다(tip 을 읽었고 tip != sha). force-push rollback 은 sha 가 끝이므로 발행한다.
 * 3. compare(base=published, head=sha)가 behind 이다(발행본이 더 새롭다).
 * 하나라도 알 수 없으면 진행한다. `warning` 은 조회 오류로 판단을 못 했음을 호출자가 알리게 한다.
 */
function guardDecision({ imageRef, sha, repository, branchRef }, exec = defaultExec) {
	const published = readRevision(imageRef, exec);
	if (published.kind !== "present") {
		return {
			retag: true,
			warning: published.kind === "error",
			reason: `${published.reason}; published revision unknown, proceeding`,
		};
	}
	const revision = published.revision;
	if (revision === sha) return { retag: true, reason: `${imageRef}: already published from ${sha}` };
	let tip;
	try {
		tip = branchTip(repository, branchRef, exec);
	} catch (error) {
		return {
			retag: true,
			warning: true,
			reason: `${imageRef}: tip of ${branchRef} unknown (${firstLine(error.message)}); proceeding`,
		};
	}
	if (tip === sha) {
		return {
			retag: true,
			reason: `${imageRef}: ${sha} is the current tip of ${branchRef} (published ${revision}); publishing`,
		};
	}
	let status;
	try {
		status = compareStatus(repository, revision, sha, exec);
	} catch (error) {
		return {
			retag: true,
			warning: true,
			reason: `${imageRef}: compare ${revision}...${sha} failed (${firstLine(error.message)}); proceeding`,
		};
	}
	if (status === "behind") {
		return {
			retag: false,
			reason: `${imageRef} is published from ${revision}, which is newer than ${sha}, and ${branchRef} is now at ${tip}; skipping retag of a stale re-run`,
		};
	}
	return { retag: true, reason: `${imageRef}: ${sha} is ${status} relative to published ${revision}` };
}

function main(argv, { exec = defaultExec, stdout = process.stdout, stderr = process.stderr } = {}) {
	const [command, ...rest] = argv;
	if (command === "verify") {
		const [imageRef, sha] = rest;
		if (!imageRef || !SHA_RE.test(sha ?? "")) {
			stderr.write("usage: image-revision.js verify <image-ref> <40-hex sha>\n");
			return 2;
		}
		// stdout 은 호출자가 $(...) 로 digest 만 받으므로, 진단·annotation 은 stderr 로 쓴다.
		let result;
		try {
			result = inspectPinned(imageRef, exec);
		} catch (error) {
			stderr.write(`::error::${imageRef} is not readable in the registry: ${error.message}\n`);
			return 1;
		}
		if (result.revision !== sha) {
			stderr.write(
				`::error::${imageRef} (${result.digest}) carries revision ${result.revision ?? "<none>"}, expected ${sha}; its build for this run did not publish\n`,
			);
			return 1;
		}
		stderr.write(`${imageRef} -> ${result.digest} (revision ${sha})\n`);
		stdout.write(`${result.digest}\n`);
		return 0;
	}
	if (command === "guard") {
		const [imageRef, sha, repository, branchRef] = rest;
		if (!imageRef || !SHA_RE.test(sha ?? "") || !REPO_RE.test(repository ?? "") || !branchNameOf(branchRef)) {
			stderr.write("usage: image-revision.js guard <image-ref> <40-hex sha> <owner/repo> <refs/heads/branch>\n");
			return 2;
		}
		const decision = guardDecision({ imageRef, sha, repository, branchRef }, exec);
		if (!decision.retag) {
			stdout.write(`::notice title=Stale re-run::${decision.reason}\n`);
			return GUARD_SKIP_EXIT;
		}
		stdout.write(decision.warning ? `::warning title=Stale re-run guard::${decision.reason}\n` : `${decision.reason}\n`);
		return 0;
	}
	stderr.write("usage: image-revision.js <verify|guard> ...\n");
	return 2;
}

module.exports = {
	GUARD_SKIP_EXIT,
	REVISION_LABEL,
	SHA_RE,
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
};

if (require.main === module) {
	process.exitCode = main(process.argv.slice(2));
}
