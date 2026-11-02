const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const version = "1.32.1";
const scripts = ["apply-tag-version.js", "sync-version.js", "check-version-sync.js", "check-version-sync.sh"];

function project(t, { rootVersion = version, frontendVersion = rootVersion, kollaTag = "latest" } = {}) {
	const directory = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-version-"));
	t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
	for (const child of ["scripts", "frontend", "backend", "helm/afterglow", "deploy/kolla"]) {
		fs.mkdirSync(path.join(directory, child), { recursive: true });
	}
	for (const script of scripts) fs.copyFileSync(path.join(__dirname, script), path.join(directory, "scripts", script));
	fs.writeFileSync(path.join(directory, "package.json"), JSON.stringify({ name: "version-fixture", version: rootVersion }));
	fs.writeFileSync(path.join(directory, "frontend/package.json"), JSON.stringify({ version: frontendVersion }));
	// A real dependency-free uv project keeps version propagation offline, without replacing the lock command.
	fs.writeFileSync(path.join(directory, "backend/pyproject.toml"), `[project]\nname = "version-fixture"\nversion = "${rootVersion}"\nrequires-python = ">=3.11"\ndependencies = []\n`);
	fs.writeFileSync(path.join(directory, "helm/afterglow/Chart.yaml"), `version: ${rootVersion}\nappVersion: "${rootVersion}"\n`);
	fs.writeFileSync(path.join(directory, "deploy/kolla/globals.afterglow.sample.yml"), `afterglow_image_tag: "${kollaTag}"\n`);
	return directory;
}

function run(directory, script, { ref = "", args = [] } = {}) {
	const env = { ...process.env, GITHUB_REF: ref, UV_OFFLINE: "true", UV_PYTHON_DOWNLOADS: "never" };
	const executable = script.endsWith(".sh") ? "bash" : process.execPath;
	const result = spawnSync(executable, [path.join(directory, "scripts", script), ...args], {
		cwd: directory, env, encoding: "utf8", timeout: 30000,
	});
	assert.ifError(result.error);
	return { status: result.status, output: result.stdout + result.stderr };
}

function assertSynced(directory, expected, kollaTag) {
	assert.equal(JSON.parse(fs.readFileSync(path.join(directory, "package.json"), "utf8")).version, expected);
	assert.equal(JSON.parse(fs.readFileSync(path.join(directory, "frontend/package.json"), "utf8")).version, expected);
	assert.match(fs.readFileSync(path.join(directory, "backend/pyproject.toml"), "utf8"), new RegExp(`^version = "${expected.replaceAll(".", "\\.")}"$`, "m"));
	assert.match(fs.readFileSync(path.join(directory, "backend/uv.lock"), "utf8"), new RegExp(`name = "version-fixture"\\nversion = "${expected.replaceAll(".", "\\.")}"`));
	assert.equal(fs.readFileSync(path.join(directory, "helm/afterglow/Chart.yaml"), "utf8"), `version: ${expected}\nappVersion: "${expected}"\n`);
	assert.equal(fs.readFileSync(path.join(directory, "deploy/kolla/globals.afterglow.sample.yml"), "utf8"), `afterglow_image_tag: "${kollaTag}"\n`);
}

for (const prefix of ["", "v"]) {
	for (const kollaTag of ["1.32.0", "v1.32.0"]) {
		test(`apply-tag uses ${prefix || "plain "}GitHub release refs ahead of CLI and replaces ${kollaTag} with the published tag`, (t) => {
			const directory = project(t, { rootVersion: "1.32.0", kollaTag });
			const result = run(directory, "apply-tag-version.js", { ref: `refs/tags/${prefix}${version}`, args: ["9.9.9"] });
			assert.equal(result.status, 0, result.output);
			assertSynced(directory, version, `${prefix}${version}`);
		});
	}
}

for (const tag of [version, `v${version}`, `refs/tags/${version}`, `refs/tags/v${version}`]) {
	for (const kollaTag of ["1.32.0", "v1.32.0"]) {
		test(`apply-tag accepts explicit ${tag} outside a tag event and replaces ${kollaTag} with the published tag`, (t) => {
			const directory = project(t, { rootVersion: "1.32.0", kollaTag });
			const result = run(directory, "apply-tag-version.js", { ref: "refs/heads/dev", args: [tag] });
			assert.equal(result.status, 0, result.output);
			assertSynced(directory, version, tag.replace(/^refs\/tags\//, ""));
		});
	}
}

for (const tag of ["", "release-1.32.1", "1.32", "v1.32.1junk", "1.32.1/extra", "01.32.1", "1.32.1-rc1", "1.32.1+build"]) {
	test(`apply-tag rejects malformed release ref ${JSON.stringify(tag)} without CLI fallback or mutation`, (t) => {
		const directory = project(t);
		const before = fs.readFileSync(path.join(directory, "package.json"));
		const result = run(directory, "apply-tag-version.js", { ref: `refs/tags/${tag}`, args: [version] });
		assert.equal(result.status, 1, result.output);
		assert.match(result.output, /apply-tag-version: 잘못된 버전 형식/);
		assert.deepEqual(fs.readFileSync(path.join(directory, "package.json")), before);
		assert.equal(fs.existsSync(path.join(directory, "backend/uv.lock")), false);
	});
}

test("apply-tag requires a release ref or explicit argument", (t) => {
	const result = run(project(t), "apply-tag-version.js", { ref: "refs/heads/dev" });
	assert.equal(result.status, 1, result.output);
	assert.match(result.output, /argv\[2\] 필요/);
});

for (const script of ["check-version-sync.js", "check-version-sync.sh"]) {
	for (const kollaTag of [version, `v${version}`, "latest", "stable"]) {
		test(`${script} accepts ${kollaTag} Kolla pins and both release ref styles`, (t) => {
			const directory = project(t, { kollaTag });
			for (const ref of [`refs/tags/${version}`, `refs/tags/v${version}`, "refs/heads/dev", ""]) {
				const result = run(directory, script, { ref });
				assert.equal(result.status, 0, result.output);
			}
		});
	}
	for (const tag of ["1.32.2", "v1.32.2"]) {
		test(`${script} rejects mismatching release ref ${tag}`, (t) => {
			const result = run(project(t), script, { ref: `refs/tags/${tag}` });
			assert.equal(result.status, 1, result.output);
			assert.match(result.output, /git tag .* ≠ package\.json/);
		});
	}
	test(`${script} rejects every malformed tag ref rather than treating it as a branch`, (t) => {
		const directory = project(t);
		for (const tag of ["", "release-1.32.1", "v", "1.32", "1.32.1junk", "v1.32.1/extra", "01.32.1", "1.32.1-rc1"]) {
			const result = run(directory, script, { ref: `refs/tags/${tag}` });
			assert.equal(result.status, 1, `${tag}: ${result.output}`);
			assert.match(result.output, /invalid release tag/);
		}
	});
	test(`${script} rejects mismatching metadata independently of tag refs`, (t) => {
		const result = run(project(t, { frontendVersion: "1.32.0" }), script);
		assert.equal(result.status, 1, result.output);
		assert.match(result.output, /version mismatch/);
	});
	test(`${script} rejects mismatching and malformed Kolla release pins`, (t) => {
		for (const kollaTag of ["1.32.0", "v1.32.0", "v1.32.1junk", "release-1.32.1", "01.32.1", ""]) {
			const result = run(project(t, { kollaTag }), script);
			assert.equal(result.status, 1, `${kollaTag}: ${result.output}`);
			assert.match(result.output, /version mismatch/);
		}
	});
}

for (const kollaTag of ["1.31.9", "v1.31.9", "latest", "stable"]) {
	test(`sync-version updates ${kollaTag} pins to plain releases or preserves automatic channels`, (t) => {
		const directory = project(t, { kollaTag });
		const result = run(directory, "sync-version.js");
		assert.equal(result.status, 0, result.output);
		assertSynced(directory, version, ["latest", "stable"].includes(kollaTag) ? kollaTag : version);
	});
}

for (const tag of [version, `v${version}`]) {
	for (const kollaTag of ["1.31.9", "v1.31.9", "latest", "stable"]) {
		test(`sync-version uses explicit published tag ${tag} for ${kollaTag} without changing automatic channels`, (t) => {
			const directory = project(t, { kollaTag });
			const result = run(directory, "sync-version.js", { args: [tag] });
			assert.equal(result.status, 0, result.output);
			assertSynced(directory, version, ["latest", "stable"].includes(kollaTag) ? kollaTag : tag);
		});
	}
}

test("sync-version rejects mismatched or malformed explicit release tags before metadata writes", (t) => {
	const directory = project(t, { frontendVersion: "1.32.0" });
	const before = fs.readFileSync(path.join(directory, "frontend/package.json"));
	for (const tag of ["", "1.32.0", "v1.32.0", "v1.32.1junk", "refs/tags/1.32.1"]) {
		const result = run(directory, "sync-version.js", { args: [tag] });
		assert.equal(result.status, 1, `${tag}: ${result.output}`);
		assert.match(result.output, /release tag must match root package\.json/);
		assert.deepEqual(fs.readFileSync(path.join(directory, "frontend/package.json")), before);
	}
});

test("sync-version rejects malformed root versions before metadata writes", (t) => {
	const directory = project(t, { rootVersion: "1.32.1garbage", frontendVersion: "1.32.0" });
	const before = fs.readFileSync(path.join(directory, "frontend/package.json"));
	const result = run(directory, "sync-version.js");
	assert.equal(result.status, 1, result.output);
	assert.match(result.output, /invalid version in root package\.json/);
	assert.deepEqual(fs.readFileSync(path.join(directory, "frontend/package.json")), before);
});
