#!/usr/bin/env node
// 루트 package.json version → frontend, backend, Helm, Kolla operator sample
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const rootPkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf-8"));
const version = rootPkg.version;

if (!/^\d+\.\d+\.\d+/.test(version)) {
	console.error(`invalid version in root package.json: ${version}`);
	process.exit(1);
}

// 1) frontend/package.json
const fePath = path.join(root, "frontend/package.json");
const fe = JSON.parse(fs.readFileSync(fePath, "utf-8"));
fe.version = version;
fs.writeFileSync(fePath, JSON.stringify(fe, null, "\t") + "\n");

// 2) Python project versions and lockfiles
function syncPythonProject(relativeDirectory, label) {
	const directory = path.join(root, relativeDirectory);
	const pyprojectPath = path.join(directory, "pyproject.toml");
	const pyproject = fs.readFileSync(pyprojectPath, "utf-8");
	if (!/^version\s*=\s*"[^"]*"/m.test(pyproject)) {
		console.error(`${label}/pyproject.toml: version line not found`);
		process.exit(1);
	}
	const patched = pyproject.replace(/^(version\s*=\s*)"[^"]*"/m, `$1"${version}"`);
	fs.writeFileSync(pyprojectPath, patched);
	try {
		execSync("uv lock --quiet", { cwd: directory, stdio: "inherit" });
	} catch {
		console.error(`${label}/uv.lock 갱신 실패 — uv 가 설치되어 있어야 합니다`);
		process.exit(1);
	}
}

syncPythonProject("backend", "backend");
syncPythonProject("cloud-shell", "cloud-shell");

// 4) helm/afterglow/Chart.yaml — version 및 appVersion 갱신
const chartPath = path.join(root, "helm/afterglow/Chart.yaml");
if (fs.existsSync(chartPath)) {
	let chart = fs.readFileSync(chartPath, "utf-8");
	chart = chart.replace(/^version:\s*.+$/m, `version: ${version}`);
	chart = chart.replace(/^appVersion:\s*.+$/m, `appVersion: "${version}"`);
	fs.writeFileSync(chartPath, chart);
}

// 5) deploy/kolla/globals.afterglow.sample.yml — published Afterglow image tag
const kollaSamplePath = path.join(root, "deploy/kolla/globals.afterglow.sample.yml");
let kollaSample = fs.readFileSync(kollaSamplePath, "utf-8");
if (!/^afterglow_image_tag:\s*"v[^"]+"/m.test(kollaSample)) {
	console.error("deploy/kolla/globals.afterglow.sample.yml: afterglow_image_tag line not found");
	process.exit(1);
}
kollaSample = kollaSample.replace(
	/^afterglow_image_tag:\s*"v[^"]+"/m,
	`afterglow_image_tag: "v${version}"`
);
fs.writeFileSync(kollaSamplePath, kollaSample);

console.log(`✓ version synced to ${version}`);
