const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const os = require("node:os")
const { spawnSync } = require("node:child_process")
const test = require("node:test")

const rootDir = path.resolve(__dirname, "..")

function readRepoFile(relativePath) {
	return fs.readFileSync(path.join(rootDir, relativePath), "utf8")
}

// Read a root distribution's resolved version from the real operator lock so
// installer fixtures never drift when a release promotes new tags.
function lockedVersion(distribution) {
	const lock = readRepoFile("deploy/kolla/operator/uv.lock")
	const match = lock.match(new RegExp(`\\[\\[package\\]\\]\\nname = "${distribution}"\\nversion = "([^"]+)"`))
	assert.ok(match, `operator lock has no resolved ${distribution}`)
	return match[1]
}

function decrementPatch(version) {
	const [major, minor, patch] = version.split(".").map(Number)
	assert.ok(patch > 0, `cannot derive a stale version below ${version}`)
	return `${major}.${minor}.${patch - 1}`
}

function lockedServicePackages(overrides = {}) {
	return [
		["drover", "drover", overrides.drover ?? lockedVersion("drover")],
		["lumen", "lumen", lockedVersion("lumen")],
		["waygate", "waygate", lockedVersion("waygate")],
		["palimpsest", "palimpsest-client", lockedVersion("palimpsest-client")],
	]
}

function createInstalledServiceFixtures(directory, rolesDir, pythonPath, customPackages) {
	const metadataDir = path.join(directory, "python-metadata")
	const packages = customPackages || lockedServicePackages()
	for (const [role, distribution, version] of packages) {
		const roleDir = path.join(rolesDir, role)
		for (const subdirectory of ["tasks", "defaults", "templates"]) {
			fs.mkdirSync(path.join(roleDir, subdirectory), { recursive: true })
		}
		fs.writeFileSync(path.join(roleDir, "tasks/main.yml"), "---\n[]\n")
		fs.writeFileSync(path.join(roleDir, "tasks/deploy.yml"), "---\n[]\n")
		fs.writeFileSync(path.join(roleDir, "defaults/main.yml"), `${role}_services: {}\n`)
		fs.writeFileSync(path.join(roleDir, `templates/${role}.conf.j2`), "[DEFAULT]\n")
		const distInfo = path.join(metadataDir, `${distribution.replaceAll("-", "_")}-${version}.dist-info`)
		fs.mkdirSync(distInfo, { recursive: true })
		fs.writeFileSync(path.join(distInfo, "METADATA"), `Metadata-Version: 2.1\nName: ${distribution}\nVersion: ${version}\n`)
	}
	fs.mkdirSync(path.dirname(pythonPath), { recursive: true })
	fs.writeFileSync(pythonPath, '#!/usr/bin/env bash\nexport PYTHONPATH="${KOLLA_TEST_METADATA:?}"\nexec "${KOLLA_TEST_PYTHON:?}" "$@"\n', { mode: 0o755 })
	return metadataDir
}

function runGlobalsNormalizer(normalizer, ...args) {
	const kollaPython = process.env.KOLLA_PYTHON
	if (kollaPython) {
		return spawnSync(kollaPython, [normalizer, ...args], { encoding: "utf8" })
	}
	return spawnSync(
		"uv",
		["run", "--project", path.join(rootDir, "backend"), "python", normalizer, ...args],
		{ encoding: "utf8" }
	)
}

test("Afterglow health checks use probe tools present in published images", () => {
	const defaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")

	assert.match(
		defaults,
		/healthcheck:\n\s+test: \["CMD", "python", "-c", "from urllib\.request import urlopen;/
	)
	assert.match(
		defaults,
		/healthcheck:\n\s+test: \["CMD", "wget", "-q", "-O", "\/dev\/null", "http:\/\//
	)
	assert.doesNotMatch(defaults, /test: \["CMD", "curl", "-f", "http:\/\{\{ afterglow_/)
})

test("Extracted service health checks use Python available in published images", () => {
	// Sibling role files are package-owned; their healthchecks are asserted by each
	// sibling repository's own kolla-asset suite. Afterglow owns only its in-tree role.
	const defaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")
	assert.match(
		defaults,
		/healthcheck:\n\s+test: \["CMD", "python", "-c", "from urllib\.request import urlopen;/
	)
	assert.doesNotMatch(defaults, /test: \["CMD", "curl", "-f"/)
})






test("Afterglow Kolla role carries no retired K3s provisioning credential", () => {
	const templatesDir = "deploy/kolla/ansible/roles/afterglow/templates"
	const roleFiles = [
		"deploy/kolla/ansible/roles/afterglow/defaults/main.yml",
		"deploy/kolla/ansible/roles/afterglow/tasks/precheck.yml",
		"deploy/kolla/ansible/roles/afterglow/tasks/preconditions_secrets.yml",
		...fs.readdirSync(path.join(rootDir, templatesDir)).map((name) => `${templatesDir}/${name}`),
	]

	for (const roleFile of roleFiles) {
		assert.doesNotMatch(readRepoFile(roleFile), /afterglow_k3s_provisioning_token/, roleFile)
	}
})




test("Afterglow public hostname is routed by Kolla's external HAProxy frontend", () => {
	const defaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")
	const precheck = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/precheck.yml")
	const loadbalancer = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/loadbalancer.yml")
	const router = readRepoFile("deploy/kolla/ansible/roles/afterglow/templates/afterglow-public.cfg.j2")
	const sample = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")

	assert.match(defaults, /^afterglow_public_haproxy_enabled: false$/m)
	assert.match(defaults, /^afterglow_public_haproxy_fqdn: ""$/m)
	assert.match(defaults, /afterglow_haproxy_services: "\{\{ afterglow_services \| combine\(afterglow_public_haproxy_services, recursive=True\) \}\}"/)
	assert.match(defaults, /afterglow-public:\n\s+group: afterglow/)
	assert.match(precheck, /Validate Kolla public route hostname/)
	assert.match(loadbalancer, /afterglow-public\.cfg/)
	assert.match(loadbalancer, /delegate_to: "\{\{ groups\['deployment'\]\[0\] \}\}"/)
	assert.match(loadbalancer, /mode: "0755"/)
	assert.match(loadbalancer, /mode: "0644"/)
	assert.match(loadbalancer, /external-frontend-map/)
	assert.match(loadbalancer, /project_services: "\{\{ afterglow_haproxy_services \}\}"/)
	assert.match(router, /backend afterglow-public_back/)
	assert.match(router, /frontend afterglow-public-router_front/)
	assert.match(router, /use_backend afterglow-api_back if \{ path_beg \/api\/ \}/)
	assert.match(router, /acl is_mcp path \/mcp\n/)
	assert.match(router, /acl is_mcp path_beg \/mcp\/\n/)
	assert.match(router, /use_backend afterglow-api_back if is_mcp/)
	assert.match(router, /acl is_well_known path_beg \/\.well-known\//)
	assert.match(router, /use_backend afterglow-api_back if is_well_known/)
	assert.match(router, /default_backend afterglow-frontend_back/)
	assert.match(sample, /^afterglow_public_haproxy_enabled: true$/m)
	assert.match(sample, /^afterglow_public_haproxy_fqdn: "cloud\.dmslab\.re\.kr"$/m)
	assert.match(sample, /^afterglow_mcp_public_url: "https:\/\/cloud\.dmslab\.re\.kr\/mcp"$/m)
	assert.match(defaults, /^afterglow_mcp_public_url: ""$/m)
})

test("Kolla installer safely patches the standard playbook import", () => {
	const patcher = path.join(rootDir, "deploy/kolla/patch_stock_site.py")
	const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-kolla-site-"))
	const sitePath = path.join(temporaryDirectory, "site.yml")
	const original = "---\n- import_playbook: gather-facts.yml\n"

	try {
		fs.writeFileSync(sitePath, original)
		for (const action of ["install", "install", "remove"]) {
			const result = spawnSync("python3", [patcher, action, sitePath], { encoding: "utf8" })
			assert.equal(result.status, 0, result.stderr)
		}
		assert.equal(fs.readFileSync(sitePath, "utf8"), original)
		const globalsPath = path.join(temporaryDirectory, "globals.yml")
		const pluginGlobalsPath = path.join(temporaryDirectory, "afterglow-globals.yml")
		const backupPath = path.join(temporaryDirectory, "globals.yml.before-afterglow-dedup")
		const stockGlobals = "kolla_base: true\n"
		const pluginGlobals = "enable_afterglow: true\n"
		fs.writeFileSync(globalsPath, `${stockGlobals}\n---\n${pluginGlobals}`)
		fs.writeFileSync(pluginGlobalsPath, pluginGlobals)
		const normalizer = path.join(rootDir, "deploy/kolla/normalize_stock_globals.py")
		const normalization = runGlobalsNormalizer(normalizer, globalsPath, pluginGlobalsPath, backupPath)
		assert.equal(normalization.status, 0, normalization.stderr)
		assert.equal(fs.readFileSync(globalsPath, "utf8"), stockGlobals)
		assert.equal(fs.readFileSync(backupPath, "utf8"), `${stockGlobals}\n---\n${pluginGlobals}`)
		const uninstall = readRepoFile("deploy/kolla/uninstall.sh")
		const installer = readRepoFile("deploy/kolla/install.sh")
		assert.match(installer, /for inventory_vars_dir in group_vars host_vars/)
		assert.match(uninstall, /default group_vars/)
		assert.match(uninstall, /default host_vars/)
		assert.match(uninstall, /MULTINODE_INVENTORY="\$KOLLA_CONFIG_DIR\/multinode"/)
		assert.ok(
			uninstall.indexOf("patch_stock_site.py\" remove") <
				uninstall.indexOf('afterglow-site.yml" "aggregate afterglow-site.yml playbook"')
		)
		assert.match(readRepoFile("deploy/kolla/install.sh"), /globals\.d/)
		assert.match(readRepoFile("deploy/kolla/install.sh"), /patch_stock_site\.py" install/)
		assert.match(uninstall, /patch_stock_site\.py" remove/)
		assert.match(installer, /PLUGIN_CONFIG_ROOT="\$KOLLA_CONFIG_DIR\/config\/afterglow"/)
		assert.match(installer, /PLUGIN_GLOBALS="\$PLUGIN_CONFIG_ROOT\/globals\.yml"/)
		assert.match(installer, /PLUGIN_SECRETS="\$PLUGIN_CONFIG_ROOT\/secrets\.yml"/)
		assert.match(uninstall, /PLUGIN_CONFIG_ROOT="\$KOLLA_CONFIG_DIR\/config\/afterglow"/)
		assert.match(uninstall, /PLUGIN_GLOBALS="\$PLUGIN_CONFIG_ROOT\/globals\.yml"/)
		assert.match(uninstall, /PLUGIN_SECRETS="\$PLUGIN_CONFIG_ROOT\/secrets\.yml"/)
		for (const script of [installer, uninstall]) {
			assert.doesNotMatch(
				script,
				/PLUGIN_(?:GLOBALS|SECRETS)="[^"\n]*\/afterglow\//,
				"plugin variable sources must derive from the standard config root"
			)
		}
		assert.match(
			installer,
			/create_symlink_safe "\$PLUGIN_GLOBALS" "\$GLOBALS_D\/90-openstack-afterglow-globals\.yml"/
		)
		assert.match(
			installer,
			/create_symlink_safe "\$PLUGIN_SECRETS" "\$GLOBALS_D\/91-openstack-afterglow-secrets\.yml"/
		)
		assert.match(
			uninstall,
			/remove_symlink_safe "\$PLUGIN_GLOBALS" "\$GLOBALS_D\/90-openstack-afterglow-globals\.yml"/
		)
		assert.match(
			uninstall,
			/remove_symlink_safe "\$PLUGIN_SECRETS" "\$GLOBALS_D\/91-openstack-afterglow-secrets\.yml"/
		)
		for (const relativePath of [
			"deploy/kolla/README.md",
			"deploy/kolla/globals.afterglow.sample.yml",
			"deploy/kolla/passwords.afterglow.additions.yml",
		]) {
			assert.doesNotMatch(
				readRepoFile(relativePath),
				/\/etc\/kolla\/afterglow/,
				`${relativePath} still references the legacy /etc/kolla/afterglow path`
			)
		}
	} finally {
		fs.rmSync(temporaryDirectory, { recursive: true, force: true })
	}
})

test("Kolla installer loads plugin variables from the standard config root", () => {
	const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-kolla-install-"))
	const kollaConfigPath = path.join(temporaryDirectory, "etc", "kolla")
	const kollaAnsiblePath = path.join(temporaryDirectory, "share", "kolla-ansible")
	const pluginConfigRoot = path.join(kollaConfigPath, "config", "afterglow")
	const legacyConfigRoot = path.join(kollaConfigPath, "afterglow")
	const pluginGlobals = path.join(pluginConfigRoot, "globals.yml")
	const pluginSecrets = path.join(pluginConfigRoot, "secrets.yml")
	const legacyGlobals = path.join(legacyConfigRoot, "globals.yml")
	const legacySecrets = path.join(legacyConfigRoot, "secrets.yml")
	const globalsLink = path.join(
		kollaConfigPath,
		"globals.d",
		"90-openstack-afterglow-globals.yml"
	)
	const secretsLink = path.join(
		kollaConfigPath,
		"globals.d",
		"91-openstack-afterglow-secrets.yml"
	)
	const installer = path.join(rootDir, "deploy", "kolla", "install.sh")
	const uninstaller = path.join(rootDir, "deploy", "kolla", "uninstall.sh")
	const kollaBinDirectory = path.join(temporaryDirectory, "bin")
	const fakeKollaBinary = path.join(kollaBinDirectory, "kolla-ansible")
	const fakeKollaPython = path.join(kollaBinDirectory, "python")
	const pythonResult = spawnSync(
		"uv",
		[
			"run",
			"--project",
			path.join(rootDir, "backend"),
			"python",
			"-c",
			"import sys; print(sys.executable)",
		],
		{ encoding: "utf8" }
	)
	assert.equal(pythonResult.status, 0, pythonResult.stderr)
	const commandEnvironment = {
		...process.env,
		AFTERGLOW_REPO_DIR: rootDir,
		KOLLA_ANSIBLE_BIN: fakeKollaBinary,
		KOLLA_TEST_PYTHON: pythonResult.stdout.trim(),
		KOLLA_ANSIBLE_DIR: kollaAnsiblePath,
		KOLLA_CONFIG_PATH: kollaConfigPath,
	}

	try {
		commandEnvironment.KOLLA_TEST_METADATA = createInstalledServiceFixtures(
			temporaryDirectory, path.join(kollaAnsiblePath, "ansible", "roles"), fakeKollaPython
		)

		fs.mkdirSync(pluginConfigRoot, { recursive: true })
		fs.mkdirSync(legacyConfigRoot, { recursive: true })
		fs.mkdirSync(kollaBinDirectory, { recursive: true })
		fs.writeFileSync(fakeKollaBinary, "#!/usr/bin/env bash\nexit 0\n", { mode: 0o755 })
		fs.writeFileSync(
			path.join(kollaAnsiblePath, "ansible", "site.yml"),
			"---\n- import_playbook: gather-facts.yml\n"
		)
		fs.writeFileSync(path.join(kollaConfigPath, "multinode"), "[control]\ncontroller\n")
		fs.writeFileSync(path.join(kollaConfigPath, "globals.yml"), "kolla_base: true\n")
		fs.writeFileSync(pluginGlobals, "enable_afterglow: true\n", { mode: 0o640 })
		fs.writeFileSync(pluginSecrets, "afterglow_secret_key: test\n", { mode: 0o600 })
		fs.writeFileSync(legacyGlobals, "legacy: [\n", { mode: 0o640 })
		fs.writeFileSync(legacySecrets, "legacy: {\n", { mode: 0o600 })

		for (const command of [installer, installer]) {
			const result = spawnSync("bash", [command], {
				encoding: "utf8",
				env: commandEnvironment,
			})
			assert.equal(result.status, 0, result.stderr)
		}

		assert.equal(fs.readlinkSync(globalsLink), pluginGlobals)
		assert.equal(fs.readlinkSync(secretsLink), pluginSecrets)
		assert.equal(fs.realpathSync(globalsLink), fs.realpathSync(pluginGlobals))
		assert.equal(fs.realpathSync(secretsLink), fs.realpathSync(pluginSecrets))
		assert.equal(fs.statSync(pluginGlobals).mode & 0o777, 0o640)
		assert.equal(fs.statSync(pluginSecrets).mode & 0o777, 0o600)

		const uninstallResult = spawnSync("bash", [uninstaller], {
			encoding: "utf8",
			env: commandEnvironment,
		})
		assert.equal(uninstallResult.status, 0, uninstallResult.stderr)
		assert.throws(() => fs.lstatSync(globalsLink), { code: "ENOENT" })
		assert.throws(() => fs.lstatSync(secretsLink), { code: "ENOENT" })
		assert.equal(fs.existsSync(pluginGlobals), true)
		assert.equal(fs.existsSync(pluginSecrets), true)
		assert.equal(fs.statSync(pluginGlobals).mode & 0o777, 0o640)
		assert.equal(fs.statSync(pluginSecrets).mode & 0o777, 0o600)

		fs.symlinkSync(legacyGlobals, globalsLink)
		const conflictResult = spawnSync("bash", [installer], {
			encoding: "utf8",
			env: commandEnvironment,
		})
		assert.notEqual(conflictResult.status, 0)
		assert.equal(fs.readlinkSync(globalsLink), legacyGlobals)
		assert.throws(() => fs.lstatSync(secretsLink), { code: "ENOENT" })
	} finally {
		fs.rmSync(temporaryDirectory, { recursive: true, force: true })
	}
})

test("Kolla helper refusals preserve stock files", () => {
	const patcher = path.join(rootDir, "deploy/kolla/patch_stock_site.py")
	const normalizer = path.join(rootDir, "deploy/kolla/normalize_stock_globals.py")
	const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-kolla-refusal-"))
	const sitePath = path.join(temporaryDirectory, "site.yml")
	const globalsPath = path.join(temporaryDirectory, "globals.yml")
	const pluginGlobalsPath = path.join(temporaryDirectory, "afterglow-globals.yml")
	const backupPath = path.join(temporaryDirectory, "globals.yml.before-afterglow-dedup")
	const malformedSite = "# END openstack-afterglow plugin\n# BEGIN openstack-afterglow plugin\n"
	const mismatchedGlobals = "kolla_base: true\n\n---\nenable_afterglow: false\n"

	try {
		fs.writeFileSync(sitePath, malformedSite)
		const patchResult = spawnSync("python3", [patcher, "remove", sitePath], { encoding: "utf8" })
		assert.equal(patchResult.status, 1, patchResult.stderr)
		assert.match(patchResult.stderr, /managed marker is malformed/)
		assert.equal(fs.readFileSync(sitePath, "utf8"), malformedSite)

		fs.writeFileSync(globalsPath, mismatchedGlobals)
		fs.writeFileSync(pluginGlobalsPath, "enable_afterglow: true\n")
		const normalizeResult = runGlobalsNormalizer(
			normalizer,
			globalsPath,
			pluginGlobalsPath,
			backupPath
		)
		assert.equal(normalizeResult.status, 1, normalizeResult.stderr)
		assert.match(normalizeResult.stderr, /trailing document does not exactly match plugin globals/)
		assert.equal(fs.readFileSync(globalsPath, "utf8"), mismatchedGlobals)
		assert.equal(fs.existsSync(backupPath), false)
	} finally {
		fs.rmSync(temporaryDirectory, { recursive: true, force: true })
	}
})

test("Plugin lifecycle dispatchers preserve stock actions and tag isolation", () => {
	for (const service of ["afterglow"]) {
		// Sibling dispatchers are package-owned and covered by sibling kolla-asset suites.
		const dispatcher = readRepoFile(`deploy/kolla/ansible/roles/${service}/tasks/main.yml`)
		assert.doesNotMatch(dispatcher, /tags: always/)
		assert.match(dispatcher, /'config_validate', 'stop', 'deploy-containers', 'check'/)
		assert.match(dispatcher, /when: kolla_action \| default\('deploy'\) in \[.*'config'\]/)
	}
	const pluginSite = readRepoFile("deploy/kolla/site.yml")
	const afterglowPull = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/pull.yml")

	assert.match(pluginSite, /kolla_action \| default\('deploy'\) in \['deploy', 'reconfigure', 'upgrade', 'config'\]/)
	assert.match(pluginSite, /kolla_action \| default\('deploy'\) in \['deploy', 'reconfigure', 'upgrade'\]/)
	assert.match(afterglowPull, /not \(afterglow_source_mode \| default\(false\) \| bool\)/)
})

test("Plugin services derive data-plane and OpenStack topology from Kolla variables", () => {
	const afterglowDefaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")
	const afterglowDatabase = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/preconditions_db.yml")
	const afterglowPrecheck = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/precheck.yml")

	assert.match(afterglowDefaults, /afterglow_database_address: "\{\{ database_address \}\}"/)
	assert.match(afterglowDefaults, /afterglow_database_admin_user: "\{\{ database_user \}\}"/)
	assert.match(afterglowDefaults, /afterglow_valkey_port: "\{\{ valkey_server_port \}\}"/)
	assert.match(afterglowDefaults, /afterglow_valkey_password: "\{\{ valkey_master_password \| default\(''\) \}\}"/)
	assert.match(afterglowDefaults, /afterglow_sentinel_enabled: true/)
	assert.match(afterglowDefaults, /afterglow_sentinel_master_name: "\{\{ valkey_sentinel_monitor_name \}\}"/)
	assert.match(afterglowDefaults, /afterglow_sentinel_hosts: ".*groups\['valkey'\].*kolla_address\(host\).*valkey_sentinel_port.*"/)
	assert.match(afterglowDefaults, /afterglow_keystone_auth_url: "\{\{ keystone_internal_url \}\}"/)
	assert.match(afterglowDefaults, /afterglow_keystone_project_domain_name: "\{\{ default_project_domain_name \}\}"/)
	assert.match(afterglowDefaults, /afterglow_keystone_user_domain_name: "\{\{ default_user_domain_name \}\}"/)
	assert.match(afterglowDefaults, /afterglow_keystone_region_name: "\{\{ openstack_region_name \}\}"/)
	assert.match(afterglowDatabase, /login_host: "\{\{ afterglow_database_address \}\}"/)
	assert.match(afterglowPrecheck, /valkey_sentinel_port is defined/)
	assert.match(afterglowPrecheck, /valkey_sentinel_monitor_name is defined and valkey_sentinel_monitor_name \| length > 0/)

})

test("Sibling Kolla role sources are externalized to service wheels", () => {
	for (const service of ["drover", "lumen", "waygate", "palimpsest"]) {
		assert.equal(fs.existsSync(path.join(rootDir, "deploy/kolla/ansible/roles", service)), false)
	}
})

test("Drover, Waygate, and Lumen public hostnames are routed by Kolla's external HAProxy frontend without disturbing internal endpoints", () => {
	const sample = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")
		for (const service of ["drover", "waygate", "lumen"]) {
		assert.match(sample, new RegExp(`^${service}_public_haproxy_enabled: true$`, "m"))
		assert.match(sample, new RegExp(`^${service}_public_haproxy_fqdn: "${service}\\.dmslab\\.re\\.kr"$`, "m"))
	}
})



test("Kolla plugin lifecycle integrates inventory preflight, pull semantics, and upgrade sequence", () => {
	const site = readRepoFile("deploy/kolla/site.yml")
	const allInOne = readRepoFile("deploy/kolla/inventory/all-in-one.sample")
	const multinode = readRepoFile("deploy/kolla/inventory/multinode.sample")

	for (const service of ["afterglow", "waygate", "drover", "lumen", "palimpsest"]) {
		assert.match(allInOne, new RegExp(`\\[${service}:children\\]`))
		assert.match(multinode, new RegExp(`\\[${service}:children\\]`))
	}

	assert.match(site, /Custom service inventory preflight check/)
	assert.match(site, /tags:\s*\[always,\s*afterglow,\s*waygate,\s*drover,\s*lumen,\s*palimpsest\]/)
	for (const service of ["afterglow", "waygate", "drover", "lumen", "palimpsest"]) {
		assert.match(site, new RegExp(`Assert inventory group for enabled ${service}`))
		assert.match(site, new RegExp(`groups\\.get\\('${service}', \\[\\]\\) \\| length > 0`))
		assert.match(site, new RegExp(`when: enable_${service} \\| default\\(false\\) \\| bool`))
	}

	const afterglowDeploy = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/deploy.yml")
	const afterglowReconfigure = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/reconfigure.yml")
	const afterglowUpgrade = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/upgrade.yml")
	const afterglowPrecheck = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/precheck.yml")

	assert.match(afterglowDeploy, /include_tasks:\s*pull\.yml/)
	const deploySourceIndex = afterglowDeploy.indexOf("source_build.yml")
	const deployPullIndex = afterglowDeploy.indexOf("pull.yml")
	const deployPrecondIndex = afterglowDeploy.indexOf("preconditions.yml")
	const deployStartIndex = afterglowDeploy.indexOf("start.yml")
	assert.ok(deploySourceIndex < deployPullIndex, "deploy.yml must include pull.yml after source_build.yml")
	assert.ok(deployPullIndex < deployPrecondIndex, "deploy.yml must include pull.yml before preconditions.yml")
	assert.ok(deployPullIndex < deployStartIndex, "deploy.yml must include pull.yml before start.yml")

	assert.match(afterglowReconfigure, /include_tasks:\s*pull\.yml/)
	const reconfigPrecheckIndex = afterglowReconfigure.indexOf("precheck.yml")
	const reconfigPullIndex = afterglowReconfigure.indexOf("pull.yml")
	const reconfigConfigIndex = afterglowReconfigure.indexOf("config.yml")
	const reconfigStartIndex = afterglowReconfigure.indexOf("start.yml")
	assert.ok(reconfigPrecheckIndex < reconfigPullIndex, "reconfigure.yml must include pull.yml after precheck.yml")
	assert.ok(reconfigPullIndex < reconfigConfigIndex, "reconfigure.yml must include pull.yml before config.yml")
	assert.ok(reconfigPullIndex < reconfigStartIndex, "reconfigure.yml must include pull.yml before start.yml")

	assert.match(afterglowUpgrade, /include_tasks:\s*pull\.yml/)
	assert.match(afterglowUpgrade, /include_tasks:\s*seed_runtime_policies\.yml/)
	assert.match(afterglowUpgrade, /include_tasks:\s*start\.yml/)
	assert.match(afterglowUpgrade, /afterglow_start_restart:\s*true/)
	const pullIndex = afterglowUpgrade.indexOf("pull.yml")
	const seedIndex = afterglowUpgrade.indexOf("seed_runtime_policies.yml")
	const restartIndex = afterglowUpgrade.indexOf("start.yml")
	assert.ok(pullIndex < seedIndex, "upgrade.yml must include pull.yml before seed_runtime_policies.yml")
	assert.ok(seedIndex < restartIndex, "upgrade.yml must seed runtime policies before the shared start task")

	assert.match(afterglowPrecheck, /Inspect enabled remote Afterglow image manifests/)
	assert.match(afterglowPrecheck, /loop:\s*"\{\{\s*afterglow_services\s*\|\s*dict2items\s*\}\}"/)
	assert.match(afterglowPrecheck, /argv:\s*\n\s*-\s*docker\s*\n\s*-\s*manifest\s*\n\s*-\s*inspect\s*\n\s*-\s*"\{\{\s*item\.value\.image\s*\}\}"/)
	assert.match(afterglowPrecheck, /register:\s*image_checks/)
	assert.match(afterglowPrecheck, /item\.rc\s*==\s*0/)
	assert.doesNotMatch(afterglowPrecheck, /afterglow_backend_image\s*\}\}:\s*\{\{\s*afterglow_image_tag/)
	assert.doesNotMatch(afterglowPrecheck, /WARN|WARNING/)

	const afterglowStart = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/start.yml")
	assert.match(afterglowStart, /groups:\s*"\{\{ item\.value\.groups \| default\(omit\) \}\}"/)
	assert.match(afterglowStart, /network_mode:\s*"\{\{ item\.value\.network_mode \| default\(omit\) \}\}"/)
	assert.match(afterglowPrecheck, /Fail if any configured Afterglow image is inaccessible[\s\S]*?no_log:\s*true/)

	for (const service of ["afterglow"]) {
		const pull = readRepoFile(`deploy/kolla/ansible/roles/${service}/tasks/pull.yml`)
		const start = readRepoFile(`deploy/kolla/ansible/roles/${service}/tasks/start.yml`)
		assert.match(pull, /community\.docker\.docker_image/)
		assert.match(pull, /source:\s*pull/)
		assert.match(pull, /force_source:\s*true/)
		assert.match(pull, /no_log:\s*true/)
		assert.match(pull, new RegExp(`loop:\\s*"\\{\\{\\s*${service}_services\\s*\\|\\s*dict2items\\s*\\}\\}"`))
		assert.match(pull, new RegExp(`not\\s*\\(${service}_source_mode\\s*\\|\\s*default\\(false\\)\\s*\\|\\s*bool\\)`))
		assert.match(
			start,
			new RegExp(
				`pull:\\s*"\\{\\{\\s*'never'\\s+if\\s+\\(${service}_source_mode\\s*\\|\\s*default\\(false\\)\\s*\\|\\s*bool\\)\\s+else\\s+'always'\\s*\\}\\}"`,
			),
		)
	}
})

test("Kolla global topology fallbacks and Afterglow TLS settings", () => {
	const afterglowDefaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")

	assert.match(
		afterglowDefaults,
		/afterglow_public_api_base: "\{\{ internal_protocol \| default\('http'\) \}\}:\/\/\{\{ kolla_internal_fqdn \| default\(kolla_internal_vip_address\) \}\}:\{\{ afterglow_backend_port \}\}"/
	)
	assert.match(afterglowDefaults, /afterglow_openstack_interface: "\{\{ openstack_interface \| default\('internal'\) \}\}"/)
	assert.match(afterglowDefaults, /afterglow_openstack_insecure: "\{\{ openstack_insecure \| default\(false\) \}\}"/)
	assert.match(afterglowDefaults, /afterglow_openstack_cacert: "\{\{ openstack_cacert \| default\(''\) \}\}"/)
	assert.match(afterglowDefaults, /afterglow_keystone_interface: "\{\{ afterglow_openstack_interface \}\}"/)


})
test("Kolla site playbook uses dynamic include_role dispatch with inventory preflight for all services", () => {
	const site = readRepoFile("deploy/kolla/site.yml")

	// Dynamic include_role for all 5 services
	for (const service of ["afterglow", "waygate", "drover", "lumen", "palimpsest"]) {
		assert.match(site, new RegExp(`name: Apply role ${service}`))
		assert.match(site, new RegExp(`ansible\\.builtin\\.include_role:\\s*\\n\\s*name: ${service}`))
		assert.match(site, new RegExp(`apply:\\s*\\n\\s*tags: ${service}`))
		assert.match(site, new RegExp(`when: enable_${service} \\| default\\(false\\) \\| bool`))
	}

	// Ensure no static `roles:` list is used in site.yml
	assert.doesNotMatch(site, /^\s*roles:\s*\n\s*-\s*\{\s*role:\s*(?:afterglow|waygate|drover|lumen|palimpsest)/m)

	// Custom service inventory preflight task asserts non-empty group when enabled
	assert.match(site, /Custom service inventory preflight check/)
	for (const service of ["afterglow", "waygate", "drover", "lumen", "palimpsest"]) {
		assert.match(site, new RegExp(`Assert inventory group for enabled ${service}`))
		assert.match(site, new RegExp(`groups\\.get\\('${service}', \\[\\]\\) \\| length > 0`))
	}

	// HAProxy route rendering uses dynamic include_role tasks_from: loadbalancer
	for (const service of ["afterglow", "waygate", "drover", "lumen", "palimpsest"]) {
		assert.match(site, new RegExp(`Render ${service[0].toUpperCase()}${service.slice(1)} HAProxy routes`))
		assert.match(site, new RegExp(`name: ${service}\\s*\\n\\s*tasks_from: loadbalancer`))
	}
})


test("Installer and uninstaller preserve root-package roles and operator files", () => {
	const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-kolla-ownership-"))
	const kollaConfigPath = path.join(temporaryDirectory, "etc", "kolla")
	const kollaAnsiblePath = path.join(temporaryDirectory, "share", "kolla-ansible")
	const rolesDir = path.join(kollaAnsiblePath, "ansible", "roles")
	const pluginConfigRoot = path.join(kollaConfigPath, "config", "afterglow")
	const fakeKollaBinary = path.join(temporaryDirectory, "bin", "kolla-ansible")
	const pythonResult = spawnSync("uv", ["run", "--project", path.join(rootDir, "backend"), "python", "-c", "import sys; print(sys.executable)"], { encoding: "utf8" })
	assert.equal(pythonResult.status, 0, pythonResult.stderr)
	try {
		const metadataDir = createInstalledServiceFixtures(temporaryDirectory, rolesDir, path.join(temporaryDirectory, "bin", "python"))
		const commandEnvironment = {
			...process.env,
			AFTERGLOW_REPO_DIR: rootDir,
			KOLLA_ANSIBLE_BIN: fakeKollaBinary,
			KOLLA_TEST_PYTHON: pythonResult.stdout.trim(),
			KOLLA_TEST_METADATA: metadataDir,
			KOLLA_ANSIBLE_DIR: kollaAnsiblePath,
			KOLLA_CONFIG_PATH: kollaConfigPath,
		}
		fs.mkdirSync(pluginConfigRoot, { recursive: true })
		fs.writeFileSync(fakeKollaBinary, "#!/usr/bin/env bash\nexit 0\n", { mode: 0o755 })
		fs.writeFileSync(path.join(kollaAnsiblePath, "ansible", "site.yml"), "---\n- import_playbook: gather-facts.yml\n")
		fs.writeFileSync(path.join(kollaConfigPath, "multinode"), "[control]\ncontroller\n")
		fs.writeFileSync(path.join(kollaConfigPath, "globals.yml"), "kolla_base: true\n")
		const pluginGlobals = path.join(pluginConfigRoot, "globals.yml")
		const pluginSecrets = path.join(pluginConfigRoot, "secrets.yml")
		fs.writeFileSync(pluginGlobals, "enable_afterglow: true\n", { mode: 0o640 })
		fs.writeFileSync(pluginSecrets, "afterglow_secret: test\n", { mode: 0o600 })
		const originalFiles = new Map()
		function snapshot(directory) {
			for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
				const file = path.join(directory, entry.name)
				if (entry.isDirectory()) snapshot(file)
				else originalFiles.set(file, fs.readFileSync(file))
			}
		}
		snapshot(rolesDir)
		snapshot(metadataDir)
		snapshot(pluginConfigRoot)
		const installer = path.join(rootDir, "deploy/kolla/install.sh")
		const uninstaller = path.join(rootDir, "deploy/kolla/uninstall.sh")
		for (const command of [installer, installer]) {
			const result = spawnSync("bash", [command], { encoding: "utf8", env: commandEnvironment })
			assert.equal(result.status, 0, result.stderr)
		}
		assert.equal(fs.readlinkSync(path.join(rolesDir, "afterglow")), path.join(rootDir, "deploy/kolla/ansible/roles/afterglow"))
		const result = spawnSync("bash", [uninstaller], { encoding: "utf8", env: commandEnvironment })
		assert.equal(result.status, 0, result.stderr)
		assert.throws(() => fs.lstatSync(path.join(rolesDir, "afterglow")), { code: "ENOENT" })
		for (const role of ["drover", "lumen", "waygate", "palimpsest"]) {
			assert.equal(fs.lstatSync(path.join(rolesDir, role)).isSymbolicLink(), false)
		}
		for (const [file, content] of originalFiles) assert.deepEqual(fs.readFileSync(file), content, file)
	} finally {
		fs.rmSync(temporaryDirectory, { recursive: true, force: true })
	}
})

test("Installer rejects stale package versions and accepts promoted operator lock versions", () => {
	const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-kolla-promoted-"))
	const kollaConfigPath = path.join(temporaryDirectory, "etc", "kolla")
	const kollaAnsiblePath = path.join(temporaryDirectory, "share", "kolla-ansible")
	const rolesDir = path.join(kollaAnsiblePath, "ansible", "roles")
	const pluginConfigRoot = path.join(kollaConfigPath, "config", "afterglow")
	const fakeKollaBinary = path.join(temporaryDirectory, "bin", "kolla-ansible")
	const pythonResult = spawnSync("uv", ["run", "--project", path.join(rootDir, "backend"), "python", "-c", "import sys; print(sys.executable)"], { encoding: "utf8" })
	assert.equal(pythonResult.status, 0, pythonResult.stderr)

	try {
		// The real operator lock already pins the promoted drover version. Model a
		// Kolla environment whose installed metadata is one patch release behind it.
		const promotedVersion = lockedVersion("drover")
		const staleVersion = decrementPatch(promotedVersion)
		const promotedLockPath = path.join(rootDir, "deploy/kolla/operator/uv.lock")

		const staleMetadataDir = createInstalledServiceFixtures(
			temporaryDirectory,
			rolesDir,
			path.join(temporaryDirectory, "bin", "python"),
			lockedServicePackages({ drover: staleVersion })
		)

		const commandEnvironment = {
			...process.env,
			AFTERGLOW_REPO_DIR: rootDir,
			AFTERGLOW_OPERATOR_LOCK: promotedLockPath,
			KOLLA_ANSIBLE_BIN: fakeKollaBinary,
			KOLLA_TEST_PYTHON: pythonResult.stdout.trim(),
			KOLLA_TEST_METADATA: staleMetadataDir,
			KOLLA_ANSIBLE_DIR: kollaAnsiblePath,
			KOLLA_CONFIG_PATH: kollaConfigPath,
		}

		fs.mkdirSync(pluginConfigRoot, { recursive: true })
		fs.writeFileSync(fakeKollaBinary, "#!/usr/bin/env bash\nexit 0\n", { mode: 0o755 })
		fs.writeFileSync(path.join(kollaAnsiblePath, "ansible", "site.yml"), "---\n- import_playbook: gather-facts.yml\n")
		fs.writeFileSync(path.join(kollaConfigPath, "multinode"), "[control]\ncontroller\n")
		fs.writeFileSync(path.join(kollaConfigPath, "globals.yml"), "kolla_base: true\n")
		fs.writeFileSync(path.join(pluginConfigRoot, "globals.yml"), "enable_afterglow: true\n", { mode: 0o640 })
		fs.writeFileSync(path.join(pluginConfigRoot, "secrets.yml"), "afterglow_secret: test\n", { mode: 0o600 })

		const installer = path.join(rootDir, "deploy/kolla/install.sh")

		// 1. Run install.sh with stale installed metadata against the promoted lock -> MUST FAIL!
		const staleResult = spawnSync("bash", [installer], { encoding: "utf8", env: commandEnvironment })
		assert.notEqual(staleResult.status, 0, "install.sh must fail when installed package version does not match promoted lock")
		assert.match(staleResult.stderr, new RegExp(`Expected drover==${promotedVersion.replaceAll(".", "\\.")} in the active Kolla environment, found '${staleVersion.replaceAll(".", "\\.")}'`))

		// 2. Upgrade installed metadata to the promoted version (simulating uv sync in Kolla environment)
		fs.rmSync(path.join(staleMetadataDir, `drover-${staleVersion}.dist-info`), { recursive: true, force: true })
		const newDistInfo = path.join(staleMetadataDir, `drover-${promotedVersion}.dist-info`)
		fs.mkdirSync(newDistInfo, { recursive: true })
		fs.writeFileSync(path.join(newDistInfo, "METADATA"), `Metadata-Version: 2.1\nName: drover\nVersion: ${promotedVersion}\n`)

		// Run install.sh with updated metadata against the promoted lock -> MUST SUCCEED!
		const successResult = spawnSync("bash", [installer], { encoding: "utf8", env: commandEnvironment })
		assert.equal(successResult.status, 0, successResult.stderr)
		assert.match(successResult.stdout, new RegExp(`Drover role verified at .* \\(drover==${promotedVersion.replaceAll(".", "\\.")}\\)`))
	} finally {
		fs.rmSync(temporaryDirectory, { recursive: true, force: true })
	}
})

test("Installer refuses a leftover retired palimpsest-local distribution", () => {
	const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-kolla-retired-"))
	const kollaConfigPath = path.join(temporaryDirectory, "etc", "kolla")
	const kollaAnsiblePath = path.join(temporaryDirectory, "share", "kolla-ansible")
	const rolesDir = path.join(kollaAnsiblePath, "ansible", "roles")
	const pluginConfigRoot = path.join(kollaConfigPath, "config", "afterglow")
	const fakeKollaBinary = path.join(temporaryDirectory, "bin", "kolla-ansible")
	const pythonResult = spawnSync("uv", ["run", "--project", path.join(rootDir, "backend"), "python", "-c", "import sys; print(sys.executable)"], { encoding: "utf8" })
	assert.equal(pythonResult.status, 0, pythonResult.stderr)

	try {
		// A controller that synchronized palimpsest-client with --inexact still has the
		// pre-rename distribution, which records ownership of the same role files.
		const metadataDir = createInstalledServiceFixtures(temporaryDirectory, rolesDir, path.join(temporaryDirectory, "bin", "python"))
		const retiredDistInfo = path.join(metadataDir, "palimpsest_local-0.2.2.dist-info")
		fs.mkdirSync(retiredDistInfo, { recursive: true })
		fs.writeFileSync(path.join(retiredDistInfo, "METADATA"), "Metadata-Version: 2.1\nName: palimpsest-local\nVersion: 0.2.2\n")

		fs.mkdirSync(pluginConfigRoot, { recursive: true })
		fs.writeFileSync(fakeKollaBinary, "#!/usr/bin/env bash\nexit 0\n", { mode: 0o755 })
		fs.writeFileSync(path.join(kollaAnsiblePath, "ansible", "site.yml"), "---\n- import_playbook: gather-facts.yml\n")
		fs.writeFileSync(path.join(kollaConfigPath, "multinode"), "[control]\ncontroller\n")
		fs.writeFileSync(path.join(kollaConfigPath, "globals.yml"), "kolla_base: true\n")
		fs.writeFileSync(path.join(pluginConfigRoot, "globals.yml"), "enable_afterglow: true\n", { mode: 0o640 })
		fs.writeFileSync(path.join(pluginConfigRoot, "secrets.yml"), "afterglow_secret: test\n", { mode: 0o600 })
		const commandEnvironment = {
			...process.env,
			AFTERGLOW_REPO_DIR: rootDir,
			KOLLA_ANSIBLE_BIN: fakeKollaBinary,
			KOLLA_TEST_PYTHON: pythonResult.stdout.trim(),
			KOLLA_TEST_METADATA: metadataDir,
			KOLLA_ANSIBLE_DIR: kollaAnsiblePath,
			KOLLA_CONFIG_PATH: kollaConfigPath,
		}
		const installer = path.join(rootDir, "deploy/kolla/install.sh")

		const retiredResult = spawnSync("bash", [installer], { encoding: "utf8", env: commandEnvironment })
		assert.notEqual(retiredResult.status, 0, "install.sh must refuse a leftover palimpsest-local distribution")
		assert.match(retiredResult.stderr, /Retired distribution palimpsest-local==0\.2\.2 is still installed/)
		assert.equal(fs.existsSync(path.join(rolesDir, "afterglow")), false, "no link may be created before the refusal")

		fs.rmSync(retiredDistInfo, { recursive: true, force: true })
		const successResult = spawnSync("bash", [installer], { encoding: "utf8", env: commandEnvironment })
		assert.equal(successResult.status, 0, successResult.stderr)
		assert.match(successResult.stdout, new RegExp(`Palimpsest role verified at .* \\(palimpsest-client==${lockedVersion("palimpsest-client").replaceAll(".", "\\.")}\\)`))
	} finally {
		fs.rmSync(temporaryDirectory, { recursive: true, force: true })
	}
})

test("Kolla Git-role promoter behavioral regressions", () => {

	const unitResult = spawnSync(
		"uv",
		["run", "--no-project", "--python", "3.11", "python", "-m", "unittest", "scripts/test_promote_kolla_role_tags.py"],
		{ cwd: rootDir, encoding: "utf8" }
	)
	assert.equal(unitResult.status, 0, unitResult.stderr || unitResult.stdout)
})


