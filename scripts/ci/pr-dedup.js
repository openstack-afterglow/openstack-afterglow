#!/usr/bin/env node
"use strict";

// docker-build.yml `pr-dedup` 잡의 PR 중복 테스트 제거 판단(CLAUDE.md "CI 파이프라인 성능 규정" 9번).
//
// 규칙: 아래를 모두 만족할 때만 skip=true 다. 그 외 모든 경로와 모든 오류는 skip=false(테스트 실행)다.
// - head repository 가 이 저장소다(fork PR 은 항상 테스트한다. fork 의 동명 `dev` 브랜치도 여기서 걸러진다).
// - PR 작성자가 dependabot 이 아니다(dependabot PR 은 항상 테스트한다).
// - head ref 가 `dev` 다. 브랜치 이름은 추가 조건일 뿐 단독 근거가 아니다.
// - head SHA 가 40자리 소문자 hex 다.
// - checkout 한 PR merge commit 의 tree 가 head commit 의 tree 와 같다. 같은 tree 는 dev push 실행이 테스트한다.
//
// skip=true 는 dev push 실행이 같은 입력을 테스트한다는 뜻이지 그 실행이 통과했다는 뜻이 아니다. notice 에
// head commit 링크를 남기고, 병합자는 그 commit 의 dev push 실행이 green 인지 확인한다.
//
// main() 은 항상 exit 0 이고 skip 을 GITHUB_OUTPUT 에 정확히 한 번, 마지막에 쓴다. 이 스크립트를 실행하지
// 못하면(checkout 실패 등) workflow step 의 fallback 이 skip=false 를 쓴다.

const fs = require("node:fs");
const { execFileSync } = require("node:child_process");

const SHA_RE = /^[0-9a-f]{40}$/;
const DEDUP_HEAD_REF = "dev";
const DEPENDABOT_RE = /^dependabot(\[bot\])?$/i;

function defaultExec(cmd, args) {
	return execFileSync(cmd, args, {
		encoding: "utf8",
		stdio: ["ignore", "pipe", "pipe"],
		timeout: 120_000,
	});
}

function firstLine(error) {
	const message = error && typeof error.message === "string" ? error.message : String(error);
	return message.split("\n")[0];
}

/**
 * skip 판단. 반환값 { skip, message }. skip=true 는 두 tree 가 같은 유효한 hash 일 때만 나온다.
 * git 오류는 throw 하며 main() 이 skip=false 로 처리한다.
 * @param {object} input
 * @param {string} [input.headRepo] github.event.pull_request.head.repo.full_name
 * @param {string} [input.baseRepo] github.repository
 * @param {string} [input.headRef] github.head_ref (공격자가 정하는 값이므로 출력하지 않는다)
 * @param {string} [input.headSha] github.event.pull_request.head.sha
 * @param {string} [input.author] github.event.pull_request.user.login
 * @param {string} [input.serverUrl] GITHUB_SERVER_URL
 */
function decide(input, exec = defaultExec) {
	const { headRepo, baseRepo, headRef, headSha, author } = input;
	if (!headRepo || !baseRepo || headRepo !== baseRepo) {
		return { skip: false, message: `head repository ${headRepo || "(unknown)"} is not ${baseRepo || "(unknown)"}; testing` };
	}
	if (DEPENDABOT_RE.test(author || "")) {
		return { skip: false, message: "dependabot pull request; testing" };
	}
	if (headRef !== DEDUP_HEAD_REF) {
		return { skip: false, message: `head ref is not ${DEDUP_HEAD_REF}; testing` };
	}
	if (!SHA_RE.test(headSha || "")) {
		return { skip: false, message: "head SHA is malformed; testing" };
	}
	exec("git", ["fetch", "--no-tags", "--depth=1", "origin", headSha]);
	const mergeTree = String(exec("git", ["rev-parse", "HEAD^{tree}"])).trim();
	const headTree = String(exec("git", ["rev-parse", `${headSha}^{tree}`])).trim();
	if (SHA_RE.test(mergeTree) && mergeTree === headTree) {
		const commitUrl = `${input.serverUrl || "https://github.com"}/${baseRepo}/commit/${headSha}`;
		return {
			skip: true,
			message:
				`PR merge tree ${mergeTree} equals dev head ${headSha} tree; the dev push run for that commit tests the same input. ` +
				`Confirm that run passed before merging: ${commitUrl}`,
		};
	}
	return { skip: false, message: `merge tree ${mergeTree || "(none)"} differs from head tree ${headTree || "(none)"}; testing` };
}

function main(env = process.env, { exec = defaultExec, stdout = process.stdout } = {}) {
	let skip = false;
	try {
		const result = decide(
			{
				headRepo: env.HEAD_REPO,
				baseRepo: env.BASE_REPO,
				headRef: env.HEAD_REF,
				headSha: env.HEAD_SHA,
				author: env.PR_AUTHOR,
				serverUrl: env.GITHUB_SERVER_URL,
			},
			exec,
		);
		if (result.skip === true) {
			skip = true;
			stdout.write(`::notice title=Layered Tests deduplicated::${result.message}\n`);
		} else {
			stdout.write(`${result.message}\n`);
		}
	} catch (error) {
		skip = false;
		stdout.write(`::warning title=PR dedup::PR dedup check failed (${firstLine(error)}); running Layered Tests\n`);
	}
	const line = `skip=${skip}\n`;
	stdout.write(line);
	if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT, line);
	return 0;
}

module.exports = { DEDUP_HEAD_REF, decide, main };

if (require.main === module) {
	process.exitCode = main();
}
