#!/usr/bin/env node
// CI 및 로컬에서 release version source 일치를 검증한다.
// tag push 이벤트에서는 git tag 와도 비교한다.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const rootV = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf-8")).version;
const feV = JSON.parse(fs.readFileSync(path.join(root, "frontend/package.json"), "utf-8")).version;
const pyText = fs.readFileSync(path.join(root, "backend/pyproject.toml"), "utf-8");
const m = pyText.match(/^version\s*=\s*"([^"]+)"/m);
const beV = m ? m[1] : "MISSING";
const cloudShellText = fs.readFileSync(path.join(root, "cloud-shell/pyproject.toml"), "utf-8");
const cloudShellMatch = cloudShellText.match(/^version\s*=\s*"([^"]+)"/m);
const cloudShellV = cloudShellMatch ? cloudShellMatch[1] : "MISSING";
const chartText = fs.readFileSync(path.join(root, "helm/afterglow/Chart.yaml"), "utf-8");
const chartMatch = chartText.match(/^version:\s*(\S+)/m);
const chartV = chartMatch ? chartMatch[1] : "MISSING";
const kollaSampleText = fs.readFileSync(
	path.join(root, "deploy/kolla/globals.afterglow.sample.yml"),
	"utf-8"
);
const kollaSampleMatch = kollaSampleText.match(/^afterglow_image_tag:\s*"v([^"]+)"/m);
const kollaSampleV = kollaSampleMatch ? kollaSampleMatch[1] : "MISSING";

const mismatch = new Set([rootV, feV, beV, cloudShellV, chartV, kollaSampleV]).size !== 1;
if (mismatch) {
	console.error("✗ version mismatch:");
	console.error(`  root package.json                     : ${rootV}`);
	console.error(`  frontend/package.json                 : ${feV}`);
	console.error(`  backend/pyproject.toml                : ${beV}`);
	console.error(`  cloud-shell/pyproject.toml            : ${cloudShellV}`);
	console.error(`  helm/afterglow/Chart.yaml             : ${chartV}`);
	console.error(`  deploy/kolla/globals.afterglow.sample.yml: ${kollaSampleV}`);
	console.error("\n  fix: npm run version:sync");
	process.exit(1);
}

// GitHub Actions tag push 이벤트에서는 git ref 와도 비교
const ref = process.env.GITHUB_REF || "";
if (ref.startsWith("refs/tags/v")) {
	const tagV = ref.replace("refs/tags/v", "");
	if (tagV !== rootV) {
		console.error(`✗ git tag v${tagV} ≠ package.json ${rootV}`);
		console.error("  태그 푸시 전에 npm version <level> 으로 먼저 bump 하세요");
		process.exit(1);
	}
}

console.log(`✓ all versions aligned: ${rootV}`);
