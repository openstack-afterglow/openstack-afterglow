#!/usr/bin/env node
// Tag-driven version sync — CI 전용 (git add/commit 없음).
//
// 사용:
//   node scripts/apply-tag-version.js          # GITHUB_REF 환경변수에서 읽음
//   node scripts/apply-tag-version.js 1.32.1  # 직접 지정 (기존 v 접두사도 허용)
//
// 동작:
//   1) tag 에서 semver 추출
//   2) root package.json version 갱신
//   3) scripts/sync-version.js 위임 → frontend/backend/uv.lock 전파

"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const ref = process.env.GITHUB_REF || "";
const source = ref.startsWith("refs/tags/") ? ref : process.argv[2];
if (!source) {
	console.error("apply-tag-version: GITHUB_REF=refs/tags/X.Y.Z 또는 argv[2] 필요");
	process.exit(1);
}
const tag = source.replace(/^refs\/tags\//, "");
const version = tag.replace(/^v/, "");
if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)) {
	console.error(`apply-tag-version: 잘못된 버전 형식: ${source}`);
	process.exit(1);
}

const root = path.resolve(__dirname, "..");
const rootPkgPath = path.join(root, "package.json");
const rootPkg = JSON.parse(fs.readFileSync(rootPkgPath, "utf-8"));

if (rootPkg.version === version) {
	console.log(`root package.json already at ${version} — no change needed`);
} else {
	console.log(`root package.json: ${rootPkg.version} → ${version}`);
	rootPkg.version = version;
	fs.writeFileSync(rootPkgPath, JSON.stringify(rootPkg, null, 2) + "\n");
}

const result = spawnSync("node", [path.join(__dirname, "sync-version.js"), tag], {
	cwd: root,
	stdio: "inherit",
	env: process.env,
});

if (result.status !== 0) {
	process.exit(result.status ?? 1);
}
