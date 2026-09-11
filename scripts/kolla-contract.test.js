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
	for (const service of ["waygate", "palimpsest"]) {
		const defaults = readRepoFile(`deploy/kolla/ansible/roles/${service}/defaults/main.yml`)
		assert.match(
			defaults,
			/healthcheck:\n\s+test: \["CMD", "python", "-c", "from urllib\.request import urlopen;/
		)
		assert.doesNotMatch(defaults, /test: \["CMD", "curl", "-f"/)
	}
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

test("Afterglow checks Keystone reachability from every backend host", () => {
	const precheck = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/precheck.yml")
	const reachability = precheck.slice(
		precheck.indexOf("Precheck | Verify Keystone internal endpoint from every Afterglow host"),
		precheck.indexOf("Precheck | Verify K3s internal API credentials"),
	)

	assert.match(reachability, /ansible\.builtin\.uri:/)
	assert.match(reachability, /url: "\{\{ afterglow_keystone_auth_url \}\}"/)
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
		fs.mkdirSync(path.join(kollaAnsiblePath, "ansible", "roles"), { recursive: true })
		const fixtureDroverRoleDir = path.join(kollaAnsiblePath, "ansible", "roles", "drover")
		fs.mkdirSync(path.join(fixtureDroverRoleDir, "tasks"), { recursive: true })
		fs.mkdirSync(path.join(fixtureDroverRoleDir, "defaults"), { recursive: true })
		fs.mkdirSync(path.join(fixtureDroverRoleDir, "templates"), { recursive: true })
		fs.writeFileSync(path.join(fixtureDroverRoleDir, "tasks", "main.yml"), "---\n- name: Drover main\n  ansible.builtin.debug:\n    msg: drover\n")
		fs.writeFileSync(path.join(fixtureDroverRoleDir, "tasks", "deploy.yml"), "---\n- name: Drover deploy\n  ansible.builtin.debug:\n    msg: deploy\n")
		fs.writeFileSync(path.join(fixtureDroverRoleDir, "defaults", "main.yml"), "drover_services: {}\n")
		fs.writeFileSync(path.join(fixtureDroverRoleDir, "templates", "drover.conf.j2"), "[drover]\n")

		const fixtureLumenRoleDir = path.join(kollaAnsiblePath, "ansible", "roles", "lumen")
		fs.mkdirSync(path.join(fixtureLumenRoleDir, "tasks"), { recursive: true })
		fs.mkdirSync(path.join(fixtureLumenRoleDir, "defaults"), { recursive: true })
		fs.mkdirSync(path.join(fixtureLumenRoleDir, "templates"), { recursive: true })
		fs.writeFileSync(path.join(fixtureLumenRoleDir, "tasks", "main.yml"), "---\n- name: Lumen main\n  ansible.builtin.debug:\n    msg: lumen\n")
		fs.writeFileSync(path.join(fixtureLumenRoleDir, "tasks", "deploy.yml"), "---\n- name: Lumen deploy\n  ansible.builtin.debug:\n    msg: deploy\n")
		fs.writeFileSync(path.join(fixtureLumenRoleDir, "defaults", "main.yml"), "lumen_services: {}\n")
		fs.writeFileSync(path.join(fixtureLumenRoleDir, "templates", "lumen.conf.j2"), "[lumen]\n")

		fs.mkdirSync(pluginConfigRoot, { recursive: true })
		fs.mkdirSync(legacyConfigRoot, { recursive: true })
		fs.mkdirSync(kollaBinDirectory, { recursive: true })
		fs.writeFileSync(fakeKollaBinary, "#!/usr/bin/env bash\nexit 0\n", { mode: 0o755 })
		fs.writeFileSync(
			fakeKollaPython,
			'#!/usr/bin/env bash\nif [[ "${1:-}" == "-c" && "${2:-}" == *drover-kolla* ]]; then echo "0.2.19"; exit 0; fi\nif [[ "${1:-}" == "-c" && "${2:-}" == *lumen-kolla* ]]; then echo "0.2.0"; exit 0; fi\nexec "${KOLLA_TEST_PYTHON:?}" "$@"\n',
			{ mode: 0o755 }
		)
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
	for (const service of ["afterglow", "waygate", "palimpsest"]) {
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
	const afterglowConfig = readRepoFile("deploy/kolla/ansible/roles/afterglow/templates/afterglow.kolla.conf.j2")
	const afterglowDatabase = readRepoFile("deploy/kolla/ansible/roles/afterglow/tasks/preconditions_db.yml")

	assert.match(afterglowDefaults, /afterglow_database_address: "\{\{ database_address \}\}"/)
	assert.match(afterglowDefaults, /afterglow_database_admin_user: "\{\{ database_user \}\}"/)
	assert.match(afterglowDefaults, /afterglow_valkey_port: "\{\{ valkey_server_port \}\}"/)
	assert.match(afterglowDefaults, /afterglow_valkey_password: "\{\{ valkey_master_password \| default\(''\) \}\}"/)
	assert.match(afterglowDefaults, /afterglow_keystone_auth_url: "\{\{ keystone_internal_url \}\}"/)
	assert.match(afterglowDefaults, /afterglow_keystone_project_domain_name: "\{\{ default_project_domain_name \}\}"/)
	assert.match(afterglowDefaults, /afterglow_keystone_user_domain_name: "\{\{ default_user_domain_name \}\}"/)
	assert.match(afterglowDefaults, /afterglow_keystone_region_name: "\{\{ openstack_region_name \}\}"/)
	assert.match(afterglowConfig, /auth_url = "\{\{ afterglow_keystone_auth_url \}\}"/)
	assert.match(afterglowConfig, /project_domain_name = "\{\{ afterglow_keystone_project_domain_name \}\}"/)
	assert.match(afterglowDatabase, /login_host: "\{\{ afterglow_database_address \}\}"/)

	for (const service of ["waygate", "palimpsest"]) {
		const defaults = readRepoFile(`deploy/kolla/ansible/roles/${service}/defaults/main.yml`)
		const template = readRepoFile(`deploy/kolla/ansible/roles/${service}/templates/${service}.conf.j2`)
		const database = readRepoFile(`deploy/kolla/ansible/roles/${service}/tasks/preconditions_db.yml`)

		assert.match(defaults, new RegExp(`${service}_database_address: "\\{\\{ database_address \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_database_port: "\\{\\{ database_port \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_database_admin_user: "\\{\\{ database_user \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_valkey_host: "\\{\\{ 'api' \\| kolla_address\\(groups\\['valkey'\\]\\[0\\]\\) \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_valkey_port: "\\{\\{ valkey_server_port \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_valkey_password: "\\{\\{ valkey_master_password`))
		assert.match(defaults, new RegExp(`${service}_keystone_auth_url: "\\{\\{ keystone_internal_url \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_keystone_project_domain_name: "\\{\\{ default_project_domain_name \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_keystone_user_domain_name: "\\{\\{ default_user_domain_name \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_keystone_region_name: "\\{\\{ openstack_region_name \\}\\}"`))
		assert.match(defaults, new RegExp(`${service}_keystone_interface: "(?:\\{\\{\\s*(?:openstack_interface\\s*\\|\\s*default\\('internal'\\)|afterglow_openstack_interface)\\s*\\}\\}|internal)"`))
		assert.match(template, new RegExp(`auth_url = "\\{\\{ ${service}_keystone_auth_url \\}\\}"`))
		assert.match(template, new RegExp(`url = "\\{\\{ ${service}_database_url \\}\\}"`))
		assert.match(database, new RegExp(`login_host: "\\{\\{ ${service}_database_address \\}\\}"`))
	}
})

test("Drover and Lumen Kolla role sources are externalized to service wheels", () => {
	assert.equal(fs.existsSync(path.join(rootDir, "deploy/kolla/ansible/roles/drover")), false)
	assert.equal(fs.existsSync(path.join(rootDir, "deploy/kolla/ansible/roles/lumen")), false)
})

test("Drover, Waygate, and Lumen public hostnames are routed by Kolla's external HAProxy frontend without disturbing internal endpoints", () => {
	const sample = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")
	for (const service of ["waygate"]) {
		const defaults = readRepoFile(`deploy/kolla/ansible/roles/${service}/defaults/main.yml`)
		const precheck = readRepoFile(`deploy/kolla/ansible/roles/${service}/tasks/precheck.yml`)
		const loadbalancer = readRepoFile(`deploy/kolla/ansible/roles/${service}/tasks/loadbalancer.yml`)

		assert.match(defaults, new RegExp(`^${service}_public_haproxy_enabled: false$`, "m"))
		assert.match(defaults, new RegExp(`^${service}_public_haproxy_fqdn: ""$`, "m"))
		assert.match(
			defaults,
			new RegExp(`${service}_haproxy_services: "\\{\\{ ${service}_services \\| combine\\(${service}_public_haproxy_services, recursive=True\\) \\}\\}"`)
		)
		assert.match(defaults, new RegExp(`${service}-public:\\n\\s+group: ${service}`))
		assert.match(defaults, new RegExp(`external_fqdn: "\\{\\{ ${service}_public_haproxy_fqdn \\}\\}"`))
		assert.match(defaults, new RegExp(`port: "\\{\\{ ${service}_api_port \\}\\}"`))
		// The internal <service>-api entry must remain non-external so
		// internal/admin Keystone endpoints keep the internal VIP listener.
		assert.match(defaults, new RegExp(`${service}-api:\\n\\s+enabled: "\\{\\{ enable_${service}_api \\| bool \\}\\}"\\n\\s+external: false`))

		assert.match(precheck, new RegExp(`Validate ${service[0].toUpperCase()}${service.slice(1)} public route hostname`))
		assert.ok(
			precheck.includes(
				`- (${service}_public_endpoint_url | regex_replace('/$', '')) == ('https://' ~ ${service}_public_haproxy_fqdn)`
			)
		)
		assert.match(loadbalancer, new RegExp(`${service}-public\\.cfg`))
		assert.match(loadbalancer, /external-frontend-map/)
		assert.match(loadbalancer, new RegExp(`project_services: "\\{\\{ ${service}_haproxy_services \\}\\}"`))
	}

	for (const service of ["drover", "waygate", "lumen"]) {
		assert.match(sample, new RegExp(`^${service}_public_haproxy_enabled: true$`, "m"))
		assert.match(sample, new RegExp(`^${service}_public_haproxy_fqdn: "${service}\\.dmslab\\.re\\.kr"$`, "m"))
	}
})

test("Waygate validates every configured runtime image reference before mutation", () => {
	const deploy = readRepoFile("deploy/kolla/ansible/roles/waygate/tasks/deploy.yml")
	const reconfigure = readRepoFile(
		"deploy/kolla/ansible/roles/waygate/tasks/reconfigure.yml"
	)
	const upgrade = readRepoFile("deploy/kolla/ansible/roles/waygate/tasks/upgrade.yml")
	const pull = readRepoFile("deploy/kolla/ansible/roles/waygate/tasks/pull.yml")
	const precheck = readRepoFile("deploy/kolla/ansible/roles/waygate/tasks/precheck.yml")
	const imagePrecheck = readRepoFile(
		"deploy/kolla/ansible/roles/waygate/tasks/image_precheck.yml"
	)
	const validator = readRepoFile(
		"deploy/kolla/ansible/roles/waygate/files/validate_image_ref.py"
	)

	assert.ok(
		deploy.indexOf("Include precheck tasks") <
			deploy.indexOf("Include precondition tasks")
	)
	assert.ok(
		reconfigure.indexOf("Include precheck tasks") <
			reconfigure.indexOf("Include config tasks")
	)
	assert.ok(
		upgrade.indexOf("Include pull tasks") <
			upgrade.indexOf("Include bootstrap service tasks")
	)
	assert.ok(
		pull.indexOf("Include Waygate image precheck tasks") <
			pull.indexOf("Pull | Pull Waygate images")
	)
	assert.match(precheck, /include_tasks: image_precheck\.yml/)
	assert.match(pull, /include_tasks: image_precheck\.yml/)
	assert.match(imagePrecheck, /Validate enabled Waygate image references/)
	assert.match(imagePrecheck, /Inspect enabled remote Waygate image manifests/)
	assert.match(imagePrecheck, /loop: "\{\{ waygate_services \| dict2items \}\}"/)
	assert.match(imagePrecheck, /- "\{\{ item\.value\.image \}\}"/)
	assert.match(
		imagePrecheck,
		/- "\{\{ waygate_source_mode \| default\(false\) \| bool \| lower \}\}"/
	)
	assert.match(imagePrecheck, /- manifest/)
	assert.match(imagePrecheck, /- inspect/)
	assert.doesNotMatch(imagePrecheck, /failed_when: false/)
	assert.doesNotMatch(imagePrecheck, /waygate_api_image \}\}:\{\{ waygate_image_tag/)
	assert.match(validator, /@sha256:\[0-9a-f\]\{64\}/)
	assert.match(validator, /afterglow-local\/waygate-/)
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
	const runtimeMountSources = [
		...defaults.matchAll(/^\s+- "([^"]+):\/app\/[^"]+:ro"$/gm),
	].map((match) => match[1])
	assert.equal(runtimeMountSources.length, 7)
	for (const source of runtimeMountSources) {
		assert.ok(source.startsWith("{{ afterglow_runtime_config_dir }}/"))
	}
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
test("Palimpsest Hub standalone Kolla role structure and contracts", () => {
	const defaults = readRepoFile("deploy/kolla/ansible/roles/palimpsest/defaults/main.yml")
	const precheck = readRepoFile("deploy/kolla/ansible/roles/palimpsest/tasks/precheck.yml")
	const imagePrecheck = readRepoFile("deploy/kolla/ansible/roles/palimpsest/tasks/image_precheck.yml")
	const sourceBuild = readRepoFile("deploy/kolla/ansible/roles/palimpsest/tasks/source_build.yml")
	const bootstrap = readRepoFile("deploy/kolla/ansible/roles/palimpsest/tasks/bootstrap_service.yml")
	const keystone = readRepoFile("deploy/kolla/ansible/roles/palimpsest/tasks/preconditions_keystone.yml")
	const validator = readRepoFile("deploy/kolla/ansible/roles/palimpsest/files/validate_image_ref.py")
	const sample = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")
	const afterglowDefaults = readRepoFile("deploy/kolla/ansible/roles/afterglow/defaults/main.yml")

	// 1. Immutable source SHA & repo
	assert.match(defaults, /palimpsest_source_version: "98f6dc920af43d0ce906750d918a60ca2f3eacd9"/)
	assert.match(afterglowDefaults, /^afterglow_backend_port: 8000$/m)
	assert.match(afterglowDefaults, /^afterglow_backend_listen_port: 18000$/m)
	assert.match(defaults, /palimpsest_source_repo: "https:\/\/github\.com\/openstack-afterglow\/palimpsest\.git"/)

	// 2. Exact image targets
	assert.match(sourceBuild, /path: "\{\{ palimpsest_source_dir \}\}\/hub"/)
	assert.match(sourceBuild, /dockerfile: "Dockerfile"/)
	assert.match(sourceBuild, /- palimpsest-hub-api/)
	assert.match(sourceBuild, /- palimpsest-hub-worker/)
	assert.match(defaults, /palimpsest-hub-api/)
	assert.match(defaults, /palimpsest-hub-worker/)

	// 3. Ports, commands, health path
	assert.match(defaults, /palimpsest_api_port: 8020/)
	assert.match(defaults, /palimpsest_api_listen_port: 18020/)
	assert.match(defaults, /command: \["uvicorn", "palimpsest_hub\.main:app".*"--port", "\{\{ palimpsest_api_listen_port \| string \}\}"/)
	assert.match(defaults, /command: \["palimpsest-hub-worker"\]/)
	assert.match(defaults, /\/v1\/health/)

	// 4. Redis DB index 9 & volume
	assert.match(defaults, /palimpsest_redis_db_index: 9/)
	assert.match(defaults, /palimpsest_hub_volume: "palimpsest_hub"/)
	assert.match(defaults, /palimpsest_hub_path: "\/var\/lib\/palimpsest\/hub"/)

	// 5. Keystone project/user/service/type
	assert.match(keystone, /type: palimpsest/)
	assert.match(keystone, /name: palimpsest/)
	assert.match(defaults, /palimpsest_service_project_name: "palimpsest-service"/)
	assert.match(defaults, /palimpsest_keystone_user: "palimpsest"/)
	assert.match(defaults, /OS_PROJECT_NAME: "\{\{ palimpsest_service_project_name \}\}"/)
	assert.match(defaults, /mysql\+asyncmy:/)

	// 6. Bootstrap command & no automatic data migration
	assert.match(bootstrap, /command: \["palimpsest-hub-bootstrap"\]/)
	assert.match(bootstrap, /OS_PROJECT_NAME: "\{\{ palimpsest_service_project_name \}\}"/)
	assert.doesNotMatch(bootstrap, /palimpsest-hub-migrate-data/)

	// 7. No old embedded worker in Afterglow role/defaults
	assert.doesNotMatch(afterglowDefaults, /enable_afterglow_palimpsest_worker/)
	assert.doesNotMatch(afterglowDefaults, /python.*app\.palimpsest_worker/)
	assert.doesNotMatch(sample, /enable_afterglow_palimpsest_worker/)
	assert.doesNotMatch(readRepoFile("Dockerfile"), /\/var\/lib\/afterglow\/palimpsest/)

	// 8. Image reference validator
	assert.match(validator, /afterglow-local\/palimpsest-hub-/)
})

test("Kolla plugin requires stock Kolla Valkey dependency and rejects standalone Redis", () => {
	const sample = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")
	assert.match(sample, /enable_valkey:\s*"yes"/)

	const expectedRoles = [
		{ name: "afterglow", dbIndex: 5 },
		{ name: "waygate", dbIndex: 6 },
		{ name: "palimpsest", dbIndex: 9 },
	]

	for (const { name: service, dbIndex } of expectedRoles) {
		const defaults = readRepoFile(`deploy/kolla/ansible/roles/${service}/defaults/main.yml`)
		assert.match(defaults, new RegExp(`${service}_valkey_host: "\\{\\{ 'api' \\| kolla_address\\(groups\\['valkey'\\]\\[0\\]\\) \\}\\}"`))
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
	assert.match(sampleGlobals, /^drover_api_image_ref:.*@sha256:/m)
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

	for (const service of ["afterglow", "waygate", "palimpsest"]) {
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

	for (const service of ["waygate", "palimpsest"]) {
		const defaults = readRepoFile(`deploy/kolla/ansible/roles/${service}/defaults/main.yml`)
		assert.match(defaults, new RegExp(`${service}_keystone_interface: "\\{\\{ openstack_interface \\| default\\('internal'\\) \\}\\}"`))
		assert.match(
			defaults,
			new RegExp(
				`${service}_internal_endpoint_url: "\\{\\{ internal_protocol \\| default\\('http'\\) \\}\\}:\\/\\/\\{\\{ kolla_internal_fqdn \\| default\\(kolla_internal_vip_address\\) \\}\\}:\\{\\{ ${service}_api_port \\}\\}"`
			)
		)
	}
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

test("Drover and Lumen Kolla role packaging, operator specifications, and installer contracts", () => {
	// 1. Drover and Lumen source roles removed from Afterglow repo
	assert.equal(fs.existsSync(path.join(rootDir, "deploy/kolla/ansible/roles/drover")), false)
	assert.equal(fs.existsSync(path.join(rootDir, "deploy/kolla/ansible/roles/lumen")), false)

	// 2. Installer & uninstaller symlink contracts
	const installer = readRepoFile("deploy/kolla/install.sh")
	const uninstaller = readRepoFile("deploy/kolla/uninstall.sh")

	assert.doesNotMatch(installer, /create_symlink_safe[^"\n]*roles\/drover/)
	assert.doesNotMatch(installer, /create_symlink_safe[^"\n]*roles\/lumen/)
	assert.doesNotMatch(uninstaller, /remove_symlink_safe[^"\n]*roles\/drover/)
	assert.doesNotMatch(uninstaller, /remove_symlink_safe[^"\n]*roles\/lumen/)

	// 3. Exact wheel URL, SHA256, and Kolla source commit in operator pyproject.toml
	const pyproject = readRepoFile("deploy/kolla/operator/pyproject.toml")
	assert.match(
		pyproject,
		/drover-kolla @ https:\/\/github\.com\/openstack-afterglow\/drover\/releases\/download\/v0\.2\.19\/drover_kolla-0\.2\.19-py3-none-any\.whl#sha256=9d11fdc3a07240a3d613ba878102668b0f9b5cf35b5bd3f3ce6e033426a12392/
	)
	assert.match(
		pyproject,
		/lumen-kolla @ https:\/\/github\.com\/openstack-afterglow\/lumen\/releases\/download\/v0\.2\.0\/lumen_kolla-0\.2\.0-py3-none-any\.whl#sha256=d55e2b0ace06d232452f9dd2892a88912755e9d00e99de0e59d6738c5a3b2474/
	)
	assert.match(
		pyproject,
		/kolla-ansible @ git\+https:\/\/opendev\.org\/openstack\/kolla-ansible@34daacfbf2d5987f543787f57535b2bebe7dee19/
	)
	assert.match(pyproject, /requires-python = ">=3\.11"/)

	// 4. Operator globals/secrets preservation
	const sampleGlobals = readRepoFile("deploy/kolla/globals.afterglow.sample.yml")
	assert.match(sampleGlobals, /^enable_drover: "yes"$/m)
	assert.match(sampleGlobals, /^drover_public_haproxy_enabled: true$/m)
	assert.match(sampleGlobals, /^drover_public_haproxy_fqdn: "drover\.dmslab\.re\.kr"$/m)
	assert.match(sampleGlobals, /^enable_lumen: "yes"$/m)
	assert.match(sampleGlobals, /^lumen_public_haproxy_enabled: true$/m)
	assert.match(sampleGlobals, /^lumen_public_haproxy_fqdn: "lumen\.dmslab\.re\.kr"$/m)
})

test("Hermetic integration test for drover-kolla and lumen-kolla wheel installation, Ansible dispatch, and uninstall safety", () => {
	const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "drover-lumen-kolla-hermetic-"))
	const kollaConfigPath = path.join(temporaryDirectory, "etc", "kolla")
	const kollaAnsiblePath = path.join(temporaryDirectory, "share", "kolla-ansible")
	const rolesDir = path.join(kollaAnsiblePath, "ansible", "roles")
	const droverRoleDir = path.join(rolesDir, "drover")
	const droverDistInfoDir = path.join(rolesDir, "drover_kolla-0.2.19.dist-info")
	const lumenRoleDir = path.join(rolesDir, "lumen")
	const lumenDistInfoDir = path.join(rolesDir, "lumen_kolla-0.2.0.dist-info")

	const pluginConfigRoot = path.join(kollaConfigPath, "config", "afterglow")
	const pluginGlobals = path.join(pluginConfigRoot, "globals.yml")
	const pluginSecrets = path.join(pluginConfigRoot, "secrets.yml")

	const installer = path.join(rootDir, "deploy", "kolla", "install.sh")
	const uninstaller = path.join(rootDir, "deploy", "kolla", "uninstall.sh")
	const kollaBinDirectory = path.join(temporaryDirectory, "bin")
	const fakeKollaBinary = path.join(kollaBinDirectory, "kolla-ansible")

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
		// 1. Setup mock installed drover-kolla 0.2.19 and lumen-kolla 0.2.0 wheel files in Python share/roles
		fs.mkdirSync(path.join(droverRoleDir, "defaults"), { recursive: true })
		fs.mkdirSync(path.join(droverRoleDir, "tasks"), { recursive: true })
		fs.mkdirSync(path.join(droverRoleDir, "templates"), { recursive: true })
		fs.mkdirSync(droverDistInfoDir, { recursive: true })

		fs.writeFileSync(path.join(droverRoleDir, "defaults", "main.yml"), "drover_services: {}\n")
		fs.writeFileSync(path.join(droverRoleDir, "tasks", "main.yml"), "---\n- name: Drover main task\n  ansible.builtin.debug:\n    msg: drover\n")
		fs.writeFileSync(path.join(droverRoleDir, "tasks", "deploy.yml"), "---\n- name: Drover deploy task\n  ansible.builtin.debug:\n    msg: deploy\n")
		fs.writeFileSync(path.join(droverRoleDir, "templates", "drover.conf.j2"), "[DEFAULT]\n")
		fs.writeFileSync(path.join(droverDistInfoDir, "METADATA"), "Metadata-Version: 2.1\nName: drover-kolla\nVersion: 0.2.19\n")

		fs.mkdirSync(path.join(lumenRoleDir, "defaults"), { recursive: true })
		fs.mkdirSync(path.join(lumenRoleDir, "tasks"), { recursive: true })
		fs.mkdirSync(path.join(lumenRoleDir, "templates"), { recursive: true })
		fs.mkdirSync(lumenDistInfoDir, { recursive: true })

		fs.writeFileSync(path.join(lumenRoleDir, "defaults", "main.yml"), "lumen_services: {}\n")
		fs.writeFileSync(path.join(lumenRoleDir, "tasks", "main.yml"), "---\n- name: Lumen main task\n  ansible.builtin.debug:\n    msg: lumen\n")
		fs.writeFileSync(path.join(lumenRoleDir, "tasks", "deploy.yml"), "---\n- name: Lumen deploy task\n  ansible.builtin.debug:\n    msg: deploy\n")
		fs.writeFileSync(path.join(lumenRoleDir, "templates", "lumen.conf.j2"), "[DEFAULT]\n")
		fs.writeFileSync(path.join(lumenDistInfoDir, "METADATA"), "Metadata-Version: 2.1\nName: lumen-kolla\nVersion: 0.2.0\n")

		// Verify package roles are real package directories, not symlinks
		assert.equal(fs.statSync(droverRoleDir).isDirectory(), true)
		assert.equal(fs.lstatSync(droverRoleDir).isSymbolicLink(), false)
		assert.match(fs.readFileSync(path.join(droverDistInfoDir, "METADATA"), "utf8"), /Version: 0\.2\.19/)

		assert.equal(fs.statSync(lumenRoleDir).isDirectory(), true)
		assert.equal(fs.lstatSync(lumenRoleDir).isSymbolicLink(), false)
		assert.match(fs.readFileSync(path.join(lumenDistInfoDir, "METADATA"), "utf8"), /Version: 0\.2\.0/)

		// 2. Setup mock Afterglow source role links targets & Kolla environment
		for (const role of ["afterglow", "waygate", "palimpsest"]) {
			fs.mkdirSync(path.join(rootDir, "deploy", "kolla", "ansible", "roles", role), { recursive: true })
		}
		fs.mkdirSync(pluginConfigRoot, { recursive: true })
		fs.mkdirSync(kollaBinDirectory, { recursive: true })

		const fakeKollaPython = path.join(kollaBinDirectory, "python")
		fs.writeFileSync(fakeKollaBinary, "#!/usr/bin/env bash\nexit 0\n", { mode: 0o755 })
		fs.writeFileSync(
			fakeKollaPython,
			'#!/usr/bin/env bash\nif [[ "${1:-}" == "-c" && "${2:-}" == *drover-kolla* ]]; then echo "0.2.19"; exit 0; fi\nif [[ "${1:-}" == "-c" && "${2:-}" == *lumen-kolla* ]]; then echo "0.2.0"; exit 0; fi\nexec "${KOLLA_TEST_PYTHON:?}" "$@"\n',
			{ mode: 0o755 }
		)
		fs.writeFileSync(path.join(kollaAnsiblePath, "ansible", "site.yml"), "---\n- import_playbook: gather-facts.yml\n")
		fs.writeFileSync(path.join(kollaConfigPath, "multinode"), "[control]\ncontroller\n[drover]\ncontroller\n[lumen]\ncontroller\n")
		fs.writeFileSync(path.join(kollaConfigPath, "globals.yml"), "kolla_base: true\n")
		fs.writeFileSync(pluginGlobals, "enable_drover: true\nenable_lumen: true\n", { mode: 0o640 })
		fs.writeFileSync(pluginSecrets, "drover_secret: test\nlumen_secret: test\n", { mode: 0o600 })

		// 3. Run installer in environment
		const installResult = spawnSync("bash", [installer], {
			encoding: "utf8",
			env: commandEnvironment,
		})
		assert.equal(installResult.status, 0, installResult.stderr)

		// Verify symlinks for repository roles were created
		for (const role of ["afterglow", "waygate", "palimpsest"]) {
			const roleLink = path.join(rolesDir, role)
			assert.equal(fs.existsSync(roleLink), true)
			assert.equal(fs.lstatSync(roleLink).isSymbolicLink(), true)
		}

		// Verify package-installed drover and lumen roles remain real directories (NO symlinks created over them)
		for (const roleDir of [droverRoleDir, lumenRoleDir]) {
			assert.equal(fs.lstatSync(roleDir).isSymbolicLink(), false)
			assert.equal(fs.statSync(roleDir).isDirectory(), true)
			assert.equal(fs.existsSync(path.join(roleDir, "tasks", "main.yml")), true)
		}

		// 4. Run uninstaller in environment
		const uninstallResult = spawnSync("bash", [uninstaller], {
			encoding: "utf8",
			env: commandEnvironment,
		})
		assert.equal(uninstallResult.status, 0, uninstallResult.stderr)

		// Verify repository role symlinks removed
		for (const role of ["afterglow", "waygate", "palimpsest"]) {
			const roleLink = path.join(rolesDir, role)
			assert.throws(() => fs.lstatSync(roleLink), { code: "ENOENT" })
		}

		// Verify package-installed drover and lumen roles and operator files remain UNTOUCHED
		for (const roleDir of [droverRoleDir, lumenRoleDir]) {
			assert.equal(fs.existsSync(roleDir), true)
			assert.equal(fs.statSync(roleDir).isDirectory(), true)
			assert.equal(fs.lstatSync(roleDir).isSymbolicLink(), false)
		}
		assert.equal(fs.existsSync(pluginGlobals), true)
		assert.equal(fs.existsSync(pluginSecrets), true)
	} finally {
		fs.rmSync(temporaryDirectory, { recursive: true, force: true })
	}
})
