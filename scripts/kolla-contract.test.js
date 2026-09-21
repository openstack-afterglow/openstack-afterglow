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

function createInstalledServiceFixtures(directory, rolesDir, pythonPath, customPackages) {
	const metadataDir = path.join(directory, "python-metadata")
	const packages = customPackages || [
		["drover", "drover", "0.2.22"],
		["lumen", "lumen", "0.2.2"],
		["waygate", "waygate", "0.1.3"],
		["palimpsest", "palimpsest-local", "0.1.4"],
	]
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

test("Afterglow public endpoint controls every browser-facing origin", () => {
	const defaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")
	const precheck = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/precheck.yml")
	const config = readRepoFile("deploy/kolla/ansible/roles/afterglow/templates/afterglow.conf.j2")
	const sample = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")

	assert.match(defaults, /^afterglow_public_endpoint_url: /m)
	assert.match(defaults, /ORIGIN: "\{\{ afterglow_public_endpoint_url \}\}"/)
	assert.match(defaults, /afterglow_instance_health_callback_base_url: "\{\{ afterglow_public_endpoint_url \}\}"/)
	assert.match(precheck, /afterglow_public_endpoint_url must be an absolute HTTP\(S\) origin/)
	assert.match(config, /frontend_base_url = "\{\{ afterglow_public_endpoint_url \}\}"/)
	assert.match(config, /origins = "\{\{ afterglow_public_endpoint_url \}\}"/)
	assert.match(config, /redirect_uri = "\{\{ afterglow_public_endpoint_url \}\}\/auth\/gitlab\/callback"/)
	assert.match(sample, /^afterglow_public_api_base: "https:\/\/cloud\.dmslab\.re\.kr"$/m)
	assert.match(sample, /^afterglow_public_endpoint_url: "https:\/\/cloud\.dmslab\.re\.kr"$/m)
	assert.doesNotMatch(defaults, /afterglow_external_url/)
})

test("Afterglow resolves the global service project once per play batch", () => {
	const config = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/config.yml")
	const lookup = config.slice(
		config.indexOf("Config | Resolve Afterglow service project ID"),
		config.indexOf("Config | Set resolved Afterglow service project ID"),
	)

	assert.match(lookup, /become: true/)
	assert.match(lookup, /no_log: true/)
	assert.match(lookup, /run_once: true/)
})

test("Afterglow fails prechecks before restart when K3s API credentials are absent", () => {
	const defaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")
	const precheck = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/precheck.yml")
	const secrets = readRepoFile(
		"deploy/kolla/ansible/roles/afterglow/tasks/preconditions_secrets.yml"
	)

	assert.match(defaults, /^afterglow_k3s_gpu_admission_token: ""$/m)
	assert.match(defaults, /^afterglow_k3s_provisioning_token: ""$/m)
	for (const taskFile of [precheck, secrets]) {
		assert.match(taskFile, /afterglow_k3s_gpu_admission_token \| length >= 32/)
		assert.match(taskFile, /afterglow_k3s_provisioning_token \| length >= 32/)
		assert.match(taskFile, /afterglow_service_k3s_enabled \| bool/)
	}
})

test("Afterglow checks the Keystone public catalog endpoint from every backend host", () => {
	const precheck = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/precheck.yml")
	const reachability = precheck.slice(
		precheck.indexOf("Precheck | Verify Keystone public catalog endpoint from every Afterglow host"),
		precheck.indexOf("Precheck | Verify K3s internal API credentials"),
	)

	assert.match(reachability, /ansible\.builtin\.uri:/)
	assert.match(reachability, /url: "\{\{ keystone_public_url \| regex_replace\('\/\$', ''\) \}\}\/v3"/)
	assert.match(reachability, /timeout: 10/)
	assert.match(reachability, /validate_certs: "\{\{ not \(afterglow_openstack_insecure \| bool\) \}\}"/)
	assert.match(reachability, /ca_path: "\{\{ afterglow_openstack_cacert \| default\(omit, true\) \}\}"/)
	assert.match(reachability, /inventory_hostname in groups\['afterglow'\]/)
	assert.doesNotMatch(reachability, /run_once:|delegate_to:/)
})

test("Afterglow frontend receives only a public runtime configuration", () => {
	const defaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")
	const vars = readRepoFile("deploy/kolla/ansible/roles/afterglow/vars/main.yml")
	const config = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/config.yml")
	const publicRenderer = readRepoFile(
		"deploy/kolla/ansible/roles/afterglow/files/render_frontend_config.py"
	)
	const baseConfig = readRepoFile(
		"deploy/kolla/ansible/roles/afterglow/templates/afterglow.conf.j2"
	)
	const finalConfig = readRepoFile(
		"deploy/kolla/ansible/roles/afterglow/templates/afterglow.kolla.conf.j2"
	)
	const frontendService = defaults.slice(
		defaults.indexOf("  afterglow-frontend:"),
		defaults.indexOf("  afterglow-palimpsest-worker:"),
	)

	assert.match(defaults, /^afterglow_config_dir: "\{\{ node_custom_config \}\}\/afterglow"$/m)
	assert.match(
		defaults,
		/^afterglow_runtime_config_dir: "\{\{ afterglow_config_dir \}\}\/generated"$/m
	)
	assert.match(
		defaults,
		/^afterglow_operator_config_source: "\{\{ afterglow_config_dir \}\}\/backend\/afterglow\.conf"$/m
	)
	assert.match(
		defaults,
		/^afterglow_operator_frontend_config_source: "\{\{ afterglow_config_dir \}\}\/frontend\/afterglow\.conf"$/m
	)
	assert.match(
		defaults,
		/^afterglow_frontend_config_name: "afterglow\.frontend\.generated\.conf"$/m
	)
	assert.doesNotMatch(vars, /^afterglow_config_dir:/m)
	assert.match(
		frontendService,
		/\{\{ afterglow_runtime_config_dir \}\}\/\{\{ afterglow_frontend_config_name \}\}:\s*\/app\/afterglow\.conf:ro/
	)
	assert.doesNotMatch(
		frontendService,
		/(?:afterglow\.operator\.conf|afterglow\.zz-kolla\.conf):\/app\/afterglow(?:\.operator|\.zz-kolla)?\.conf:ro/,
	)
	assert.match(config, /Config \| Render final Kolla configuration override/)
	assert.match(config, /Config \| Render merged public frontend configuration/)
	assert.ok(
		config.indexOf("Config | Render final Kolla configuration override") <
			config.indexOf("Config | Render merged public frontend configuration")
	)
	assert.doesNotMatch(config, /executable:.*ansible_python_interpreter/)
	assert.match(config, /afterglow_frontend_config_render\.rc == 0 and/)
	assert.match(config, /render_frontend_config\.py/)
	assert.match(config, /afterglow_operator_config_source_stat\.stat\.exists/)
	assert.match(config, /afterglow_operator_frontend_config_source_stat\.stat\.exists/)
	assert.match(config, /afterglow_operator_frontend_config_name/)
	assert.match(config, /afterglow_kolla_config_name/)
	assert.match(config, /afterglow_frontend_config_name/)
	assert.match(config, /Afterglow operator source paths must not overlap generated runtime artifacts/)
	assert.match(baseConfig, /chat = \{\{ afterglow_service_chat_enabled \| bool \| lower \}\}/)
	assert.match(finalConfig, /chat = \{\{ afterglow_service_chat_enabled \| bool \| lower \}\}/)
	assert.match(publicRenderer, /_PUBLIC_SCHEMA/)
	assert.match(publicRenderer, /"public_api_base": str/)
	assert.match(publicRenderer, /"grafana_base_url": str/)
	assert.match(publicRenderer, /"base_url": str/)
	assert.match(publicRenderer, /"gitlab_url": str/)
	assert.match(publicRenderer, /"public_url": str/)
	assert.match(publicRenderer, /os\.chmod\(staging_path, 0o644\)/)
	assert.match(publicRenderer, /def main\(\*path_args: str\)/)
	assert.doesNotMatch(
		publicRenderer,
		/"(?:secret_key|password|redis_url|database_url)":/
	)
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
	assert.match(router, /default_backend afterglow-frontend_back/)
	assert.match(sample, /^afterglow_public_haproxy_enabled: true$/m)
	assert.match(sample, /^afterglow_public_haproxy_fqdn: "cloud\.dmslab\.re\.kr"$/m)
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
	const afterglowBaseConfig = readRepoFile("deploy/kolla/ansible/roles/afterglow/templates/afterglow.conf.j2")
	const afterglowConfig = readRepoFile("deploy/kolla/ansible/roles/afterglow/templates/afterglow.kolla.conf.j2")
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
	assert.match(afterglowConfig, /auth_url = "\{\{ afterglow_keystone_auth_url \}\}"/)
	assert.match(afterglowConfig, /project_domain_name = "\{\{ afterglow_keystone_project_domain_name \}\}"/)
	assert.match(afterglowDatabase, /login_host: "\{\{ afterglow_database_address \}\}"/)
	for (const template of [afterglowBaseConfig, afterglowConfig]) {
		assert.match(template, /sentinel_enabled = \{\{ afterglow_sentinel_enabled \| bool \| lower \}\}/)
		assert.match(template, /sentinel_master_name = "\{\{ afterglow_sentinel_master_name \}\}"/)
		assert.match(template, /sentinel_hosts = "\{\{ afterglow_sentinel_hosts \}\}"/)
	}
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

test("Afterglow hands operator TOML to containers without surrendering Kolla-owned settings", () => {
	const defaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")
	const vars = readRepoFile("deploy/kolla/ansible/roles/afterglow/vars/main.yml")
	const configTask = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/config.yml")
	const bootstrap = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/bootstrap_service.yml")
	const start = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/start.yml")
	const finalConfig = readRepoFile("deploy/kolla/ansible/roles/afterglow/templates/afterglow.kolla.conf.j2")
	const generatedConfig = readRepoFile(
		"deploy/kolla/ansible/roles/afterglow/templates/afterglow.conf.j2"
	)
	const staticBackendConfig = readRepoFile(
		"deploy/kolla/ansible/roles/afterglow/templates/afterglow-backend.json.j2"
	)
	const sample = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")
	const sanitizer = readRepoFile("deploy/kolla/ansible/roles/afterglow/files/sanitize_operator_config.py")
	const readme = readRepoFile("deploy/kolla/README.md")
	const backendService = defaults.slice(
		defaults.indexOf("  afterglow-backend:"),
		defaults.indexOf("  afterglow-frontend:"),
	)

	assert.match(defaults, /^afterglow_config_dir: "\{\{ node_custom_config \}\}\/afterglow"$/m)
	assert.match(defaults, /^afterglow_runtime_config_dir: "\{\{ afterglow_config_dir \}\}\/generated"$/m)
	assert.match(defaults, /^afterglow_operator_config_source: "\{\{ afterglow_config_dir \}\}\/backend\/afterglow\.conf"$/m)
	assert.match(defaults, /^afterglow_operator_frontend_config_source: "\{\{ afterglow_config_dir \}\}\/frontend\/afterglow\.conf"$/m)
	assert.match(defaults, /^afterglow_operator_config_name: "afterglow\.operator\.generated\.conf"$/m)
	assert.match(defaults, /^afterglow_kolla_config_name: "afterglow\.zz-kolla\.generated\.conf"$/m)
	assert.match(defaults, /^afterglow_operator_config_staging_path: "\/tmp\/\{\{ afterglow_operator_config_name \}\}\.sanitized"$/m)
	assert.doesNotMatch(vars, /^afterglow_config_dir:/m)
	assert.doesNotMatch(backendService, /GITLAB_OIDC_CLIENT_SECRET/)
	assert.doesNotMatch(staticBackendConfig, /GITLAB_OIDC_CLIENT_SECRET/)
	assert.match(
		generatedConfig,
		/client_secret = "\{\{ afterglow_oidc_client_secret \| default\(''\) \}\}"/
	)
	const directRuntimeMountSources = [
		...defaults.matchAll(/^\s+- "([^"]+):\/app\/[^"]+:ro"$/gm),
	].map((match) => match[1])
	assert.equal(directRuntimeMountSources.length, 4)
	for (const source of directRuntimeMountSources) {
		assert.ok(source.startsWith("{{ afterglow_runtime_config_dir }}/"))
	}
	assert.equal((backendService.match(/afterglow_runtime_config_dir ~ '\/'/g) ?? []).length, 3)
	assert.match(backendService, /afterglow_rbd_conf_source ~ ':\/etc\/ceph\/ceph\.conf:ro'/)
	assert.match(backendService, /afterglow_rbd_keyring_source ~ ':\/etc\/ceph\/ceph\.client\.afterglow-rbd\.keyring:ro'/)
	assert.match(backendService, /if afterglow_rbd_conf_source and afterglow_rbd_keyring_source else \[\]/)
	assert.match(configTask, /Config \| Stage and validate sanitized operator configuration/)
	assert.match(configTask, /sanitize_operator_config\.py/)
	assert.match(configTask, /Config \| Clear stale sanitized operator configuration staging file/)
	assert.match(configTask, /afterglow_operator_config_staging_path/)
	assert.match(configTask, /Config \| Remove sanitized operator configuration staging file/)
	assert.match(configTask, /Config \| Copy operator configuration override/)
	assert.match(configTask, /Config \| Project frontend source onto the public allowlist/)
	assert.match(configTask, /afterglow_operator_config_source_stat\.stat\.exists/)
	assert.match(configTask, /afterglow_operator_frontend_config_source_stat\.stat\.exists/)
	assert.match(configTask, /Afterglow operator source paths must not overlap generated runtime artifacts/)
	assert.match(configTask, /- "\{\{ ansible_playbook_python \}\}"/)
	assert.match(configTask, /src: afterglow\.kolla\.conf\.j2/)
	assert.match(sanitizer, /tomllib\.loads\(sanitized\)/)
	assert.match(sanitizer, /builder\.ssh_private_key must not be staged/)
	assert.match(bootstrap, /afterglow_operator_config_name/)
	assert.match(bootstrap, /afterglow_kolla_config_name/)
	const bootstrapMountSources = [
		...bootstrap.matchAll(/^\s+- "([^"]+):\/app\/[^"]+:ro"$/gm),
	].map((match) => match[1])
	assert.equal(bootstrapMountSources.length, 3)
	for (const source of bootstrapMountSources) {
		assert.ok(source.startsWith("{{ afterglow_runtime_config_dir }}/"))
	}
	assert.match(start, /Stat Afterglow configuration layers/)
	assert.match(start, /afterglow_config_stats\.results \| map\(attribute='stat\.checksum'\) \| join\(':'\)/)
	assert.equal((start.match(/config_hash:/g) || []).length, 1)
	const startConfigPaths = [...start.matchAll(/^\s+- "([^"]+)"$/gm)].map((match) => match[1])
	assert.equal(startConfigPaths.length, 5)
	for (const source of startConfigPaths) {
		assert.ok(source.startsWith("{{ afterglow_runtime_config_dir }}/"))
	}
	assert.match(readme, /\/etc\/kolla\/config\/afterglow\/backend\/afterglow\.conf/)
	assert.match(readme, /\/etc\/kolla\/config\/afterglow\/frontend\/afterglow\.conf/)
	assert.match(readme, /Raw operator files are never mounted into\s+containers/)
	assert.match(
		readme,
		/install -m 0600 -o .* \.\/afterglow\.conf\s+\\\s+\/etc\/kolla\/config\/afterglow\/backend\/afterglow\.conf/
	)
	assert.match(finalConfig, /^\[openstack\]$/m)
	assert.match(finalConfig, /^\[union\]$/m)
	assert.match(finalConfig, /metadata_store_share_id/)
	assert.match(finalConfig, /^\[cors\]$/m)
	assert.doesNotMatch(finalConfig, /^\[gitlab_oidc\]$/m)
	assert.doesNotMatch(sample, /^afterglow_operator_config_source:/m)
	assert.match(sample, /\/etc\/kolla\/config\/afterglow\/backend\/afterglow\.conf/)
	assert.match(sample, /\/etc\/kolla\/config\/afterglow\/frontend\/afterglow\.conf/)
})
test("Kolla plugin requires stock Kolla Valkey dependency and rejects standalone Redis", () => {
	const sample = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")
	assert.match(sample, /enable_valkey:\s*"yes"/)

	const expectedRoles = [
		{ name: "afterglow", dbIndex: 5 },
	]

	for (const { name: service, dbIndex } of expectedRoles) {
		const defaults = readRepoFile(`deploy/kolla/ansible/roles/${service}/defaults/main.yml`)
		if (service === "afterglow") {
			assert.match(defaults, /afterglow_sentinel_enabled: true/)
			assert.match(defaults, /afterglow_sentinel_master_name: "\{\{ valkey_sentinel_monitor_name \}\}"/)
			assert.match(defaults, /afterglow_sentinel_hosts: ".*groups\['valkey'\].*valkey_sentinel_port.*"/)
		} else {
			assert.match(defaults, new RegExp(`${service}_valkey_host: "\\{\\{ 'api' \\| kolla_address\\(groups\\['valkey'\\]\\[0\\]\\) \\}\\}"`))
		}
		assert.match(defaults, new RegExp(`${service}_valkey_port: "\\{\\{ valkey_server_port \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_valkey_password:`))
		assert.match(defaults, new RegExp(`${service}_valkey_password:.*valkey_master_password`))
		assert.match(defaults, new RegExp(`${service}_redis_db_index: ${dbIndex}`))
		assert.match(
			defaults,
			new RegExp(
				`${service}_redis_url: "redis://default:\\{\\{ ${service}_valkey_password \\}\\}@\\{\\{ ${service}_valkey_host \\}\\}:\\{\\{ ${service}_valkey_port \\}\\}/\\{\\{ ${service}_redis_db_index \\}\\}"`
			)
		)

		const precheck = readRepoFile(`deploy/kolla/ansible/roles/${service}/tasks/precheck.yml`)
		assert.match(precheck, /name: Precheck \| Verify stock Kolla Valkey dependency/)
		assert.match(precheck, /enable_valkey \| default\(false\) \| bool/)
		assert.match(precheck, /groups\.get\('valkey', \[\]\) \| length > 0/)
		assert.match(precheck, /valkey_master_password is defined and valkey_master_password \| length > 0/)
		if (service === "afterglow") {
			assert.match(precheck, /valkey_sentinel_port is defined/)
			assert.match(precheck, /valkey_sentinel_monitor_name is defined and valkey_sentinel_monitor_name \| length > 0/)
		}
		assert.match(precheck, new RegExp(`when: enable_${service} \\| default\\(false\\) \\| bool`))
		assert.match(precheck, /run_once: true/)
		assert.match(precheck, /tags: precheck/)
		assert.match(precheck, new RegExp(`Deploy stock Kolla Valkey before enabling ${service}; no plugin Redis fallback exists`))
	}

	const filesToScan = [
		"deploy/kolla/globals.afterglow.sample.yml",
	]

	function collectFiles(dir) {
		const entries = fs.readdirSync(dir, { withFileTypes: true })
		for (const entry of entries) {
			const fullPath = path.join(dir, entry.name)
			if (entry.isDirectory()) {
				collectFiles(fullPath)
			} else if (entry.isFile()) {
				const relPath = path.relative(rootDir, fullPath)
				filesToScan.push(relPath)
			}
		}
	}
	collectFiles(path.join(rootDir, "deploy/kolla/ansible/roles"))

	assert.strictEqual(fs.existsSync(path.join(rootDir, "deploy/kolla/ansible/roles/redis")), false)

	const forbiddenPatterns = [
		/\benable_redis\b/,
		/\broles\/redis\b/,
		/\bredis_services\b/,
		/\bredis_port\b/,
		/\benable_redis_[a-z_]+\b/,
		/\bcontainer_name:\s*"?redis\b/,
		/\bimage:\s*"?[^"\n]*\bredis:[^"\n]*/,
		/\bredis_data\b/,
		/\bredis_volume\b/,
	]

	for (const relPath of filesToScan) {
		const content = readRepoFile(relPath)
		for (const pattern of forbiddenPatterns) {
			assert.equal(
				pattern.test(content),
				false,
				`File ${relPath} matched forbidden Redis pattern ${pattern}`
			)
		}
	}
})
test("Afterglow Kolla placement-policy seeding lifecycle and container contract", () => {
	const deploy = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/deploy.yml")
	const reconfigure = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/reconfigure.yml")
	const upgrade = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/upgrade.yml")
	const seedTask = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/seed_runtime_policies.yml")
	const dockerfile = readRepoFile("Dockerfile")
	const backendStageStart = dockerfile.indexOf("FROM python:3.12-slim AS backend")
	const backendStageEnd = dockerfile.indexOf("FROM backend-builder AS backend-dev")
	assert.ok(
		backendStageStart >= 0 && backendStageEnd > backendStageStart,
		"Dockerfile must contain a bounded backend production stage"
	)
	const backendStage = dockerfile.slice(backendStageStart, backendStageEnd)

	assert.match(
		backendStage,
		/COPY\s+backend\/scripts\/\s+\.\/scripts\//,
		"Backend stage in Dockerfile must copy backend/scripts/ to ./scripts/"
	)
	assert.match(deploy, /seed_runtime_policies\.yml/)
	assert.ok(
		deploy.indexOf("bootstrap_service.yml") < deploy.indexOf("seed_runtime_policies.yml"),
		"deploy.yml must include seed_runtime_policies.yml after bootstrap_service.yml"
	)

	assert.match(reconfigure, /seed_runtime_policies\.yml/)
	assert.ok(
		reconfigure.indexOf("config.yml") < reconfigure.indexOf("seed_runtime_policies.yml"),
		"reconfigure.yml must include seed_runtime_policies.yml after config.yml"
	)

	assert.match(upgrade, /seed_runtime_policies\.yml/)
	assert.ok(
		upgrade.indexOf("pull.yml") < upgrade.indexOf("seed_runtime_policies.yml"),
		"upgrade.yml must include seed_runtime_policies.yml after image pull"
	)
	assert.ok(
		upgrade.indexOf("seed_runtime_policies.yml") < upgrade.indexOf("start.yml"),
		"upgrade.yml must include seed_runtime_policies.yml before the shared start specification"
	)

	assert.match(seedTask, /image:\s*"\{\{ afterglow_backend_image_ref \}\}"/)
	assert.match(seedTask, /:\/app\/afterglow\.conf:ro/)
	assert.match(seedTask, /DATABASE_URL:\s*"\{\{ afterglow_database_url \}\}"/)
	assert.match(seedTask, /REDIS_URL:\s*"\{\{ afterglow_redis_url \}\}"/)
	assert.ok(
		seedTask.includes("python") &&
			seedTask.includes("scripts/import_runtime_infrastructure_settings.py") &&
			seedTask.includes("--config") &&
			seedTask.includes("/app/afterglow.conf") &&
			seedTask.includes("--apply"),
		"seed_runtime_policies.yml command must execute python scripts/import_runtime_infrastructure_settings.py --config /app/afterglow.conf --apply"
	)
	assert.match(seedTask, /run_once:\s*true/)
	assert.match(seedTask, /delegate_to:\s*"\{\{ groups\['afterglow'\] \| first \}\}"/)
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

	const afterglowDefaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")
	const sampleGlobals = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")
	const releaseVersion = JSON.parse(readRepoFile("package.json")).version
	const escapedReleaseVersion = releaseVersion.replaceAll(".", "\\.")
	assert.match(sampleGlobals, new RegExp(`^afterglow_image_tag:\\s*"v${escapedReleaseVersion}"$`, "m"))
	assert.match(sampleGlobals, /^afterglow_backend_image_ref: "\{\{ afterglow_backend_image \}\}:\{\{ afterglow_image_tag \}\}"$/m)
	assert.match(sampleGlobals, /^afterglow_frontend_image_ref: "\{\{ afterglow_frontend_image \}\}:\{\{ afterglow_image_tag \}\}"$/m)
	assert.match(sampleGlobals, /^afterglow_worker_image_ref: "\{\{ afterglow_worker_image \}\}:\{\{ afterglow_image_tag \}\}"$/m)
	assert.match(sampleGlobals, /^drover_api_image_ref:.*(?:@sha256:|:(?:v)?\d)/m)
	const afterglowStart = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/start.yml")
	const serviceMapStart = afterglowDefaults.indexOf("afterglow_services:")
	const environmentMapStart = afterglowDefaults.indexOf("afterglow_service_environments:")
	const serviceMap = afterglowDefaults.slice(serviceMapStart, environmentMapStart)
	assert.ok(serviceMapStart >= 0 && environmentMapStart > serviceMapStart)
	assert.doesNotMatch(serviceMap, /^\s+environment:/m)
	assert.match(afterglowStart, /env:\s*"\{\{ afterglow_service_environments\.get\(item\.key, \{\}\) \}\}"/)
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
	const afterglowKollaConf = readRepoFile("deploy/kolla/ansible/roles/afterglow/templates/afterglow.kolla.conf.j2")

	assert.match(
		afterglowDefaults,
		/afterglow_public_api_base: "\{\{ internal_protocol \| default\('http'\) \}\}:\/\/\{\{ kolla_internal_fqdn \| default\(kolla_internal_vip_address\) \}\}:\{\{ afterglow_backend_port \}\}"/
	)
	assert.match(afterglowDefaults, /afterglow_openstack_interface: "\{\{ openstack_interface \| default\('internal'\) \}\}"/)
	assert.match(afterglowDefaults, /afterglow_openstack_insecure: "\{\{ openstack_insecure \| default\(false\) \}\}"/)
	assert.match(afterglowDefaults, /afterglow_openstack_cacert: "\{\{ openstack_cacert \| default\(''\) \}\}"/)
	assert.match(afterglowDefaults, /afterglow_keystone_interface: "\{\{ afterglow_openstack_interface \}\}"/)

	assert.match(afterglowKollaConf, /^insecure = \{\{ afterglow_openstack_insecure \| bool \| lower \}\}$/m)
	assert.match(afterglowKollaConf, /^cacert = "\{\{ afterglow_openstack_cacert \}\}"$/m)

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
		// Create an isolated promoted uv.lock where drover is promoted to 0.2.23
		const promotedLockPath = path.join(temporaryDirectory, "uv.lock")
		const currentLock = fs.readFileSync(path.join(rootDir, "deploy/kolla/operator/uv.lock"), "utf8")
		const promotedLock = currentLock.replace(
			/name = "drover"\nversion = "0\.2\.22"/,
			'name = "drover"\nversion = "0.2.23"'
		)
		fs.writeFileSync(promotedLockPath, promotedLock)

		// Set up environment where installed metadata still has stale drover 0.2.22
		const staleMetadataDir = createInstalledServiceFixtures(
			temporaryDirectory,
			rolesDir,
			path.join(temporaryDirectory, "bin", "python"),
			[
				["drover", "drover", "0.2.22"],
				["lumen", "lumen", "0.2.2"],
				["waygate", "waygate", "0.1.3"],
				["palimpsest", "palimpsest-local", "0.1.4"],
			]
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

		// 1. Run install.sh with stale metadata (0.2.22) against promoted lock (0.2.23) -> MUST FAIL!
		const staleResult = spawnSync("bash", [installer], { encoding: "utf8", env: commandEnvironment })
		assert.notEqual(staleResult.status, 0, "install.sh must fail when installed package version does not match promoted lock")
		assert.match(staleResult.stderr, /Expected drover==0\.2\.23 in the active Kolla environment, found '0\.2\.22'/)

		// 2. Upgrade installed metadata to 0.2.23 (simulating uv sync in Kolla environment)
		fs.rmSync(path.join(staleMetadataDir, "drover-0.2.22.dist-info"), { recursive: true, force: true })
		const newDistInfo = path.join(staleMetadataDir, "drover-0.2.23.dist-info")
		fs.mkdirSync(newDistInfo, { recursive: true })
		fs.writeFileSync(path.join(newDistInfo, "METADATA"), "Metadata-Version: 2.1\nName: drover\nVersion: 0.2.23\n")

		// Run install.sh with updated metadata (0.2.23) against promoted lock -> MUST SUCCEED!
		const successResult = spawnSync("bash", [installer], { encoding: "utf8", env: commandEnvironment })
		assert.equal(successResult.status, 0, successResult.stderr)
		assert.match(successResult.stdout, /Drover role verified at .* \(drover==0\.2\.23\)/)
	} finally {
		fs.rmSync(temporaryDirectory, { recursive: true, force: true })
	}
})

test("Kolla operator tag-promotion script and workflow preserve immutable release contract", () => {
	const script = readRepoFile("scripts/promote_kolla_role_tags.py")
	const testScript = readRepoFile("scripts/test_promote_kolla_role_tags.py")
	const workflow = readRepoFile(".github/workflows/promote-kolla-role-tags.yml")
	const operatorReadme = readRepoFile("deploy/kolla/operator/README.md")
	const kollaReadme = readRepoFile("deploy/kolla/README.md")
	const installer = readRepoFile("deploy/kolla/install.sh")

	assert.match(script, /TAG_RE = re\.compile\(r"\^v/)
	assert.match(script, /def select_tag\(/)
	assert.match(script, /def verify_tag_source\(/)
	assert.match(script, /"--tag"/)
	assert.match(workflow, /schedule:\n\s+- cron: /)
	assert.match(workflow, /promote_kolla_role_tags\.py --latest/)
	assert.match(workflow, /automation\/kolla-role-tags/)
	assert.match(workflow, /git config user\.name "github-actions\[bot\]"/)
	assert.match(operatorReadme, /python3 scripts\/promote_kolla_role_tags\.py --latest/)
	assert.match(operatorReadme, /uv add --no-sync --tag vX\.Y\.Z "drover @ git\+/)
	assert.match(kollaReadme, /Each root package promotion is bound to its immutable `vX\.Y\.Z` release tag\./)
	assert.match(installer, /read_locked_version\.py/)
	assert.doesNotMatch(installer, /DROVER_VERSION="0\.2\.22"/)

	const unitResult = spawnSync(
		"uv",
		["run", "--no-project", "--python", "3.11", "python", "-m", "unittest", "scripts/test_promote_kolla_role_tags.py"],
		{ cwd: rootDir, encoding: "utf8" }
	)
	assert.equal(unitResult.status, 0, unitResult.stderr || unitResult.stdout)
})

test("Cloud Shell Kolla contract is dedicated, immutable, and fail-closed", () => {
	const defaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")
	const configTasks = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/config.yml")
	const keystone = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/preconditions_keystone.yml")
	const precheck = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/precheck_cloud_shell.yml")
	const baseConfig = readRepoFile("deploy/kolla/ansible/roles/afterglow/templates/afterglow.conf.j2")
	const finalConfig = readRepoFile("deploy/kolla/ansible/roles/afterglow/templates/afterglow.kolla.conf.j2")
	const sample = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")

	assert.match(defaults, /^afterglow_cloud_shell_project_name: "afterglow-cloud-shell"$/m)
	assert.match(defaults, /^afterglow_cloud_shell_image: ""$/m)
	assert.match(defaults, /^afterglow_service_cloud_shell_enabled: false$/m)
	assert.match(configTasks, /Config \| Resolve Cloud Shell service project ID/)
	assert.match(configTasks, /afterglow_cloud_shell_project_id != afterglow_service_project_id/)
	assert.match(keystone, /module_name: openstack\.cloud\.role_assignment/)
	assert.match(keystone, /Create exactly one project named/)
	const registration = keystone.slice(0, keystone.indexOf("Keystone | Resolve pre-created Cloud Shell project"))
	assert.doesNotMatch(registration, /afterglow_cloud_shell_project_name/)

	for (const dependency of [
		"enable_zun",
		"enable_kuryr",
		"enable_etcd",
		"docker_configure_for_zun",
		"containerd_configure_for_zun",
		"zun_configure_for_cinder_ceph",
		"zun-compute",
	]) {
		assert.match(precheck, new RegExp(dependency.replace("-", "\\-")))
	}
	assert.match(precheck, /@sha256:\[0-9a-fA-F\]\{64\}/)
	assert.match(precheck, /security group rule list --ingress/)
	assert.match(precheck, /appcontainer list -f json/)
	assert.match(precheck, /volume list --limit 1 -f json/)
	assert.match(precheck, /docker\n\s+- manifest\n\s+- inspect/)

	for (const template of [baseConfig, finalConfig]) {
		assert.match(template, /cloud_shell = \{\{ \(afterglow_service_cloud_shell_enabled/)
		assert.match(template, /\[cloud_shell\]/)
		assert.match(template, /service_project_id = "\{\{ afterglow_cloud_shell_project_id \}\}"/)
		assert.match(template, /zun_websocket_origin = "\{\{ afterglow_cloud_shell_zun_websocket_origin \}\}"/)
	}
	assert.match(sample, /afterglow_cloud_shell_image: "ghcr\.io\/openstack-afterglow\/afterglow-cloud-shell@sha256:/)
	assert.match(sample, /^afterglow_service_cloud_shell_enabled: false$/m)
})
