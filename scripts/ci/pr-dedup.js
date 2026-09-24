#!/usr/bin/env node
"use strict";

// docker-build.yml `pr-dedup` 잡의 PR 중복 테스트 제거 판단(CLAUDE.md "CI 파이프라인 성능 규정" 9번).
//
// 규칙: 아래를 모두 만족할 때만 skip=true 다. 그 외 모든 경로와 모든 오류는 skip=false(테스트 실행)다.
// - head repository 가 이 저장소다(fork PR 은 항상 테스트한다. fork 의 동명 `dev` 브랜치도 여기서 걸러진다).
// - PR 작성자가 dependabot 이 아니다(dependabot PR 은 항상 테스트한다).
// - head ref 가 `dev` 다. 브랜치 이름은 추가 조건일 뿐 단독 근거가 아니다.
// - head SHA 가 40자리 소문자 hex 이고 base repository 가 `owner/name` 형식이다.
// - checkout 한 PR merge commit 의 tree 가 head commit 의 tree 와 같다.
// - 그 head SHA 의 docker-build.yml push 실행이 존재한다(상태 무관). GitHub Actions API
//   `repos/<repo>/actions/workflows/docker-build.yml/runs?head_sha=<sha>&event=push` 로 확인한다.
//   tree 가 같아도 push 실행이 없을 수 있다. push trigger 의 paths-ignore(.argocd-source-*.yaml,
//   dev kustomization.yaml)만 바꾼 dev push 는 실행을 만들지 않는데, 그 파일도 version-check 의
//   check_architecture.py 입력이다. 실행이 0건이거나 API 오류이면 테스트한다.
//
// 실행 존재만 확인하고 결론은 보지 않는다. PR synchronize 시점에는 push 실행이 아직 진행 중이기 때문이다.
// skip=true 는 그 push 실행이 같은 입력을 테스트한다는 뜻이지 통과했다는 뜻이 아니다. notice 에 그 실행과
// head commit 링크를 남기고, 병합자는 그 실행이 green 인지 확인한다. PR 이벤트가 push 실행 생성보다 먼저
// 도착하는 경합은 실행 0건이 되어 테스트 쪽으로 실패한다.
//
// main() 은 항상 exit 0 이고 skip 을 GITHUB_OUTPUT 에 정확히 한 번, 마지막에 쓴다. 이 스크립트를 실행하지
// 못하면(checkout 실패 등) workflow step 의 fallback 이 skip=false 를 쓴다.

const fs = require("node:fs");
const { execFileSync } = require("node:child_process");

const SHA_RE = /^[0-9a-f]{40}$/;
const REPO_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const DEDUP_HEAD_REF = "dev";
const PUSH_WORKFLOW = "docker-build.yml";
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

/** `gh api` 경로. query 는 경로에 둔다(`-f` 는 `-X GET` 없이 POST 를 만든다). */
function pushRunsEndpoint(repo, headSha) {
	return `repos/${repo}/actions/workflows/${PUSH_WORKFLOW}/runs?head_sha=${headSha}&event=push&per_page=100`;
}

/**
 * head SHA 의 docker-build.yml push 실행 하나. 없으면 null. API·JSON 오류는 throw 한다.
 * API 필터를 믿지 않고 head_sha 와 event 를 다시 확인한다.
 */
function findPushRun(repo, headSha, exec = defaultExec) {
	const body = JSON.parse(String(exec("gh", ["api", pushRunsEndpoint(repo, headSha)])));
	const runs = body && typeof body === "object" && Array.isArray(body.workflow_runs) ? body.workflow_runs : [];
	return (
		runs.find(
			(run) => run && typeof run === "object" && run.head_sha === headSha && run.event === "push" && Number.isSafeInteger(run.id),
		) || null
	);
}

/**
 * skip 판단. 반환값 { skip, message }. skip=true 는 두 tree 가 같은 유효한 hash 이고 head SHA 의 push 실행이
 * 존재할 때만 나온다. git·API 오류는 throw 하며 main() 이 skip=false 로 처리한다.
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
	if (!REPO_RE.test(baseRepo)) {
		return { skip: false, message: "base repository is malformed; testing" };
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
	if (!SHA_RE.test(mergeTree) || mergeTree !== headTree) {
		return { skip: false, message: `merge tree ${mergeTree || "(none)"} differs from head tree ${headTree || "(none)"}; testing` };
	}
	const run = findPushRun(baseRepo, headSha, exec);
	if (!run) {
		return {
			skip: false,
			message:
				`merge tree equals head ${headSha} tree, but no ${PUSH_WORKFLOW} push run exists for that commit ` +
				"(a push that only touches paths-ignore creates none, or the run is not created yet); testing",
		};
	}
	const serverUrl = input.serverUrl || "https://github.com";
	return {
		skip: true,
		message:
			`PR merge tree ${mergeTree} equals dev head ${headSha} tree and push run ${run.id} tests that commit. ` +
			`Confirm that run passed before merging: ${serverUrl}/${baseRepo}/actions/runs/${run.id} ` +
			`(commit ${serverUrl}/${baseRepo}/commit/${headSha})`,
	};
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

module.exports = { DEDUP_HEAD_REF, PUSH_WORKFLOW, decide, findPushRun, main, pushRunsEndpoint };

if (require.main === module) {
	process.exitCode = main();
}
