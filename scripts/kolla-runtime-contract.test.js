const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const os = require("node:os")
const { spawnSync } = require("node:child_process")
const test = require("node:test")

const root = path.resolve(__dirname, "..")
const runtime = path.join(root, "deploy/kolla/operator/.venv/bin")
const services = ["afterglow", "waygate", "drover", "lumen", "palimpsest"]
const components = {
	afterglow: ["afterglow_backend", "afterglow_frontend", "afterglow_worker"],
	waygate: ["waygate_api", "waygate_worker"],
	drover: ["drover_api", "drover_worker"],
	lumen: ["lumen_api", "lumen_worker", "lumen_controller"],
	palimpsest: ["palimpsest_api", "palimpsest_worker"],
}
const refNames = Object.values(components).flat().map(prefix => `${prefix}_image_ref`)
const digestA = `sha256:${"a".repeat(64)}`
const digestB = `sha256:${"b".repeat(64)}`
const targetHosts = ["controller-a", "controller-b"]

// Permanent offline boundary only: the real helper still owns selection, errors
// and pin handling. A consumer can move this registry between serial batches.
const dockerBoundary = `import json, os
from types import SimpleNamespace

def record(event):
    with open(os.environ['RUNTIME_REGISTRY_EVIDENCE'], 'a') as output:
        output.write(json.dumps(event) + '\\n')

class Images:
    def get_registry_data(self, ref, auth_config=None):
        record({'event': 'lookup', 'ref': ref})
        with open(os.environ['RUNTIME_REGISTRY_STATE']) as source:
            state = json.load(source)
        if ref in state.get('fail_refs', []):
            raise RuntimeError('Descriptor unavailable')
        return SimpleNamespace(id=state['digest'])

class Client:
    images = Images()
    def close(self):
        pass

def from_env():
    record({'event': 'selection'})
    return Client()
`
const operatorTasks = [
	"Config | Check operator configuration source",
	"Config | Stage and validate sanitized operator configuration",
	"Config | Check frontend public configuration source",
	"Config | Project frontend source onto the public allowlist",
]

// Only side effects are mocked. Kolla's parser, config loading, subprocess,
// Ansible imports, includes, delegation and play-context inheritance are real.
const action = `from ansible.plugins.action import ActionBase
import json, os

class ActionModule(ActionBase):
    TRANSFERS_FILES = False
    def run(self, tmp=None, task_vars=None):
        label = self._task.args['label']
        evidence = {'label': label, 'become': bool(self._play_context.become),
                    'delegate': self._task.delegate_to,
                    'config': task_vars.get('runtime_config_marker'),
                    'action': task_vars.get('kolla_action'),
                    'host': task_vars['inventory_hostname'],
                    'refs': {name: task_vars[name] for name in json.loads(os.environ['RUNTIME_REF_NAMES']) if name in task_vars}}
        with open(os.environ['RUNTIME_EVIDENCE'], 'a') as output:
            output.write(json.dumps(evidence) + '\\n')
        if label.endswith(':deploy') and os.environ.get('RUNTIME_MOVE_DIGEST'):
            state_path = os.environ['RUNTIME_REGISTRY_STATE']
            with open(state_path) as source:
                state = json.load(source)
            if not state.get('moved'):
                state.update(digest=os.environ['RUNTIME_MOVE_DIGEST'], moved=True)
                with open(state_path, 'w') as target:
                    json.dump(state, target)
        expected = self._task.args.get('expected_become', True)
        if evidence['become'] != expected:
            return {'failed': True, 'msg': ('Missing inherited become: ' if expected else 'Unexpected operator become: ') + label}
        return {'changed': False, 'stat': {'exists': True, 'isreg': True, 'readable': True}}
`

function runFixture({ enabled = services, tags, tagOption = "--tags", lifecycle = "deploy", negative = false, standalone = false, operatorConfig = false, negativeOperator = false,
	hostVars = {}, targets = targetHosts,
	serial = false, globals = {}, extraVars = {}, registry = {}, moveDigest, invocations = 1, productionDefaults = false } = {}) {
	for (const binary of ["python", "ansible-playbook", "kolla-ansible"]) {
		assert.ok(fs.existsSync(path.join(runtime, binary)),
			`Missing operator runtime ${binary}; install deploy/kolla/operator requirements before test:kolla:runtime (no backend Ansible dependency).`)
	}
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kolla-runtime-"))
	function write(file, text) {
		fs.mkdirSync(path.dirname(path.join(dir, file)), { recursive: true })
		fs.writeFileSync(path.join(dir, file), text)
	}
	try {
		const controllers = serial ? ["excluded", ...targets] : ["controller"]
		write("multinode", ["[all]", ...controllers.map(host => `${host} ansible_connection=local${serial ? ` ansible_python_interpreter=${host === "excluded" ? "/not-a-target/python" : path.join(runtime, "python")}` : ""}`),
			"delegate ansible_connection=local", ...services.flatMap(name => [`[${name}]`, ...controllers]),
			"[loadbalancer]", ...controllers, "[deployment]", "delegate", ""].join("\n"))
		if (serial) {
			for (const host of controllers) write(`host_vars/${host}.yml`, JSON.stringify({
				...Object.fromEntries(Object.values(components).flat().map(prefix => [`${prefix}_image`,
					`${host === "excluded" ? "excluded.invalid" : "fixture.invalid"}/${prefix}`])),
				...hostVars[host],
			}))
		}
		write("globals.yml", JSON.stringify({
			...Object.fromEntries(services.map(name => [`enable_${name}`, false])),
			ansible_facts: { runtime_fixture: true },
			enable_haproxy: true, runtime_config_marker: "base",
			kolla_ansible_setup_filter: [], kolla_ansible_setup_gather_subset: ["!all"],
			...(!serial ? Object.fromEntries(refNames.map(name => [name, `fixture.invalid/${name}:1.2.3`])) : {
				kolla_serial: 1, ansible_become: false,
			}),
		}))
		write("passwords.yml", "{}\n")
		write("globals.d/10-services.yml", JSON.stringify({
			...Object.fromEntries(enabled.map(name => [`enable_${name}`, true])),
			runtime_config_marker: "globals.d-loaded",
			...globals,
		}))
		write("ansible.cfg", "[defaults]\nforks=1\nretry_files_enabled=False\nhost_key_checking=False\n")
		write("action_plugins/runtime_probe.py", action)
		write("docker-boundary/docker.py", dockerBoundary)
		write("registry-state.json", JSON.stringify({ digest: digestA, ...registry }))
		const probe = (label, delegated = false) => `- name: Probe ${label}\n  runtime_probe:\n    label: ${label}\n    expected_become: ${!serial}\n${delegated ? "  delegate_to: delegate\n" : ""}`
		for (const name of enabled) {
			write(`ansible/roles/${name}/tasks/main.yml`, "- ansible.builtin.import_tasks: deploy.yml\n")
			write(`ansible/roles/${name}/tasks/deploy.yml`, probe(`${name}:deploy`) + probe(`${name}:delegated`, true))
			write(`ansible/roles/${name}/tasks/loadbalancer.yml`, probe(`${name}:haproxy`))
		}
		for (const file of ["tasks/resolve_image_refs.yml", "files/resolve_image_refs.py"]) {
			write(`ansible/roles/afterglow/${file}`, fs.readFileSync(path.join(root, `deploy/kolla/ansible/roles/afterglow/${file}`), "utf8"))
		}
		if (productionDefaults) {
			write("ansible/roles/afterglow/defaults/main.yml",
				fs.readFileSync(path.join(root, "deploy/kolla/ansible/roles/afterglow/defaults/main.yml"), "utf8"))
		}
		if (operatorConfig) {
			write("ansible/roles/afterglow/tasks/main.yml", "- ansible.builtin.import_tasks: operator-config.yml\n- ansible.builtin.import_tasks: deploy.yml\n")
			write("operator-config-source.yml", fs.readFileSync(path.join(root, "deploy/kolla/ansible/roles/afterglow/tasks/config.yml"), "utf8"))
		}
		write("ansible/roles/loadbalancer/tasks/config.yml", probe("haproxy:config"))
		write("ansible/roles/loadbalancer/tasks/check-containers.yml", probe("haproxy:reconcile"))
		let aggregate = fs.readFileSync(path.join(root, "deploy/kolla/site.yml"), "utf8")
		if (negative) aggregate = aggregate.replace(/^  become: true\s*$/gm, "")
		write("ansible/afterglow-site.yml", aggregate)
		if (standalone) {
			for (const name of services) write(`ansible/${name}.yml`, fs.readFileSync(path.join(root, `deploy/kolla/playbooks/${name}.yml`), "utf8"))
		}
		write("ansible/site.yml", standalone
			? services.map(name => `- import_playbook: ${name}.yml`).join("\n")
			: "- import_playbook: afterglow-site.yml\n")
		write("invoke.py", `import os, sys
${operatorConfig ? `import json, yaml
# Preserve real delegation, conditions, registration and privilege declarations.
# Replace only stat/command operations with the side-effect-free action probe.
names = ${JSON.stringify(operatorTasks)}
with open('operator-config-source.yml') as source:
    selected = [task for task in yaml.safe_load(source) if task.get('name') in names]
assert [task['name'] for task in selected] == names, 'Operator source tasks missing or reordered'
for task in selected:
    operations = [key for key in task if key in ('ansible.builtin.stat', 'ansible.builtin.command')]
    assert len(operations) == 1, 'Unexpected operator task action'
    del task[operations[0]]
    task['runtime_probe'] = {'label': task['name'], 'expected_become': False}
    ${negativeOperator ? "task.pop('become', None)" : "# Keep the source become declaration unchanged."}
with open('ansible/roles/afterglow/tasks/operator-config.yml', 'w') as target:
    json.dump(selected, target)
` : ""}
from kolla_ansible import utils
# The installed stock site is replaced with a harmless import fixture only.
utils.get_data_files_path = lambda *parts: os.path.join(os.getcwd(), *parts)
sys.argv = ['kolla-ansible', ${JSON.stringify(lifecycle)}, '-i', 'multinode'] + sys.argv[1:]
from kolla_ansible.cmd.kolla_ansible import main
sys.exit(main())
`)
		// Isolate from operator credentials, inventories, callbacks and become overrides.
		const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith("ANSIBLE_") && !key.startsWith("KOLLA_")))
		const readRows = file => fs.existsSync(path.join(dir, file))
			? fs.readFileSync(path.join(dir, file), "utf8").trim().split("\n").filter(Boolean).map(JSON.parse) : []
		const results = []
		for (let invocation = 0; invocation < invocations; invocation++) {
			write("evidence.jsonl", "")
			write("registry-evidence.jsonl", "")
			const result = spawnSync(path.join(runtime, "python"), ["invoke.py", ...(tags ? [tagOption, tags] : []),
				...(serial ? ["--limit", targets.join(",")] : []), "-e", JSON.stringify(extraVars)], {
				cwd: dir, encoding: "utf8", timeout: 90000, maxBuffer: 4 * 1024 * 1024,
				env: { ...env, PATH: `${runtime}${path.delimiter}${process.env.PATH}`, KOLLA_CONFIG_PATH: dir,
					PYTHONPATH: path.join(dir, "docker-boundary"),
					ANSIBLE_CONFIG: path.join(dir, "ansible.cfg"), ANSIBLE_LOCAL_TEMP: path.join(dir, "tmp"),
					ANSIBLE_ACTION_PLUGINS: path.join(dir, "action_plugins"),
					ANSIBLE_ROLES_PATH: path.join(dir, "ansible/roles"),
					OBJC_DISABLE_INITIALIZE_FORK_SAFETY: "YES", RUNTIME_EVIDENCE: path.join(dir, "evidence.jsonl"),
					RUNTIME_REF_NAMES: JSON.stringify(refNames), RUNTIME_REGISTRY_STATE: path.join(dir, "registry-state.json"),
					RUNTIME_REGISTRY_EVIDENCE: path.join(dir, "registry-evidence.jsonl"),
					...(moveDigest ? { RUNTIME_MOVE_DIGEST: moveDigest } : {}) },
			})
			results.push({ ...result, evidence: readRows("evidence.jsonl"), registryEvidence: readRows("registry-evidence.jsonl"),
				registryState: JSON.parse(fs.readFileSync(path.join(dir, "registry-state.json"), "utf8")),
				output: `${result.stdout}\n${result.stderr}\n${result.error || ""}` })
		}
		return invocations === 1 ? results[0] : results
	} finally {
		fs.rmSync(dir, { recursive: true, force: true })
	}
}

function runPalimpsestEndpointFixture(vars, endpoints = {}) {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kolla-hub-endpoint-"))
	const script = `import json, os, pathlib, re, shutil, subprocess, sys, tomllib, yaml
root, scratch = map(pathlib.Path, sys.argv[1:3])
role = root / 'deploy/kolla/ansible/roles/afterglow'
fixture = scratch / 'ansible/roles/afterglow'
for directory in ('tasks', 'defaults', 'templates'):
    (fixture / directory).mkdir(parents=True)
for filename in ('main.yml', 'validate_palimpsest_endpoint.yml'):
    shutil.copyfile(role / 'tasks' / filename, fixture / 'tasks' / filename)
shutil.copyfile(role / 'defaults/main.yml', fixture / 'defaults/main.yml')
names = ('Config | Render generated Afterglow base layer', 'Config | Render final Kolla configuration override')
tasks = [task for task in yaml.safe_load((role / 'tasks/config.yml').read_text()) if task['name'] in names]
assert len(tasks) == 2
# Only host ownership is sandboxed; lifecycle dispatch, URL guard, destinations and templates are real.
for task in tasks:
    task['become'] = False
    task['no_log'] = False
    task['ansible.builtin.template'].pop('owner')
    task['ansible.builtin.template'].pop('group')
(fixture / 'tasks/config.yml').write_text(yaml.safe_dump(tasks))
for filename in ('afterglow.conf.j2', 'afterglow.kolla.conf.j2'):
    template = (role / 'templates' / filename).read_text()
    section = re.search(r'\\[services\\]\\n.*?(?=\\n\\[|\\Z)', template, re.S).group()
    (fixture / 'templates' / filename).write_text(section)
play = [{'hosts': 'afterglow', 'gather_facts': False, 'roles': ['afterglow']}]
(scratch / 'ansible/site.yml').write_text(yaml.safe_dump(play))
endpoints = json.loads(sys.argv[4])
hosts = list(endpoints) or ['localhost']
(scratch / 'multinode').write_text('[afterglow]\\n' + ''.join(host + ' ansible_connection=local\\n' for host in hosts))
(scratch / 'host_vars').mkdir()
for host in hosts:
    (scratch / host).mkdir()
    host_vars = {'afterglow_runtime_config_dir': str(scratch / host)}
    if host in endpoints:
        host_vars['afterglow_service_palimpsest_internal_url'] = endpoints[host]
    (scratch / 'host_vars' / (host + '.yml')).write_text(yaml.safe_dump(host_vars))
(scratch / 'globals.yml').write_text('{}\\n')
(scratch / 'passwords.yml').write_text('{}\\n')
(scratch / 'invoke.py').write_text('import os, sys\\nfrom kolla_ansible import utils\\n'
    + 'utils.get_data_files_path = lambda *parts: os.path.join(os.getcwd(), *parts)\\n'
    + "sys.argv = ['kolla-ansible', 'genconfig', '-i', 'multinode'] + sys.argv[1:]\\n"
    + 'from kolla_ansible.cmd.kolla_ansible import main\\nsys.exit(main())\\n')
variables = {'ansible_python_interpreter': sys.executable,
    'afterglow_generated_config_name': 'afterglow.conf',
    'afterglow_kolla_config_name': 'afterglow.kolla.conf', **json.loads(sys.argv[3])}
os.environ['KOLLA_CONFIG_PATH'] = str(scratch)
result = subprocess.run([sys.executable, str(scratch / 'invoke.py'), '-e', json.dumps(variables)],
    cwd=scratch, capture_output=True, text=True)
rendered = {}
if all((scratch / hosts[0] / name).exists() for name in ('afterglow.conf', 'afterglow.kolla.conf')):
    for filename in ('afterglow.conf', 'afterglow.kolla.conf'):
        rendered[filename] = tomllib.loads((scratch / hosts[0] / filename).read_text())['services']
    rendered['effective'] = {**rendered['afterglow.conf'],
        'palimpsest_internal_url': 'https://operator.example.test', **rendered['afterglow.kolla.conf']}
print(json.dumps({'status': result.returncode, 'rendered': rendered,
    'emitted': [name for name in ('afterglow.conf', 'afterglow.kolla.conf') if (scratch / hosts[0] / name).exists()],
    'emitted_by_host': {host: [name for name in ('afterglow.conf', 'afterglow.kolla.conf') if (scratch / host / name).exists()] for host in hosts},
    'output': result.stdout + result.stderr}))
`
	try {
		fs.writeFileSync(path.join(dir, "ansible.cfg"), "[defaults]\nforks=1\nretry_files_enabled=False\n")
		const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith("ANSIBLE_") && !key.startsWith("KOLLA_")))
		const result = spawnSync(path.join(runtime, "python"), ["-c", script, root, dir, JSON.stringify({
			enable_afterglow: true, afterglow_service_palimpsest_enabled: true, ...vars,
		}), JSON.stringify(endpoints)], {
			encoding: "utf8", timeout: 30000,
			env: { ...env, PATH: `${runtime}${path.delimiter}${process.env.PATH}`, ANSIBLE_CONFIG: path.join(dir, "ansible.cfg"), ANSIBLE_LOCAL_TEMP: path.join(dir, "tmp"),
				OBJC_DISABLE_INITIALIZE_FORK_SAFETY: "YES" },
		})
		assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}\n${result.error || ""}`)
		return JSON.parse(result.stdout)
	} finally {
		fs.rmSync(dir, { recursive: true, force: true })
	}
}
function expectSuccess(result, selected, haproxy = true, lifecycle = "deploy") {
	assert.equal(result.status, 0, result.output)
	assert.deepEqual(new Set(result.evidence.map(row => row.label.split(":")[0])),
		new Set([...selected, ...(haproxy ? ["haproxy"] : [])]), result.output)
	for (const row of result.evidence) {
		assert.equal(row.become, true, row.label)
		assert.equal(row.config, "globals.d-loaded", row.label)
		assert.equal(row.action, lifecycle, row.label)
		if (row.label.endsWith(":delegated")) assert.equal(row.delegate, "delegate")
	}
}

test("native kolla-ansible deploy -i multinode inherits privilege through every service and HAProxy", () => {
	expectSuccess(runFixture(), services)
})

test("native Kolla optional service tags isolate runtime execution", () => {
	expectSuccess(runFixture({ tags: "afterglow,lumen" }), ["afterglow", "lumen"])
})

test("exact native --tag reconfigure selects all five services including waygat", () => {
	const result = runFixture({ lifecycle: "reconfigure", tagOption: "--tag",
		tags: "afterglow,lumen,drover,palimpsest,waygat" })
	expectSuccess(result, services, true, "reconfigure")
})

test("native --tag waygat cannot bypass registry failure before reconfigure", () => {
	const result = runFixture({ lifecycle: "reconfigure", tagOption: "--tag", tags: "waygat", serial: true,
		globals: { waygate_image_tag: "latest", enable_waygate_api: true, enable_waygate_worker: true },
		registry: { fail_refs: ["fixture.invalid/waygate_api:latest"] } })
	assert.notEqual(result.status, 0, result.output)
	assert.match(result.output, /Cannot select exact waygate images from the registry/)
	assert.deepEqual(result.evidence, [], result.output)
	expectSelection(result, ["fixture.invalid/waygate_api:latest"])
})

test("disabled absent roles do not prevent standard deploy", () => {
	expectSuccess(runFixture({ enabled: ["afterglow", "lumen"] }), ["afterglow", "lumen"])
})

test("standalone compatibility playbooks also inherit privilege without --become", () => {
	expectSuccess(runFixture({ standalone: true }), services, false)
})

test("negative control rejects aggregate without play-level become", () => {
	const result = runFixture({ negative: true })
	assert.notEqual(result.status, 0, result.output)
	assert.match(result.output, /Missing inherited become/)
	assert.ok(result.evidence.some(row => !row.become), result.output)
})

test("real delegated operator source tasks override privileged service play with become:false", () => {
	const result = runFixture({ enabled: ["afterglow"], operatorConfig: true })
	assert.equal(result.status, 0, result.output)
	const probes = result.evidence.filter(row => operatorTasks.includes(row.label))
	assert.deepEqual(probes.map(row => row.label), operatorTasks, result.output)
	for (const row of probes) {
		assert.equal(row.become, false, row.label)
		assert.equal(row.delegate, "delegate", row.label)
	}
	expectSuccess({ ...result, evidence: result.evidence.filter(row => !operatorTasks.includes(row.label)) }, ["afterglow"])
})

test("negative control catches removed operator privilege override under privileged service play", () => {
	const result = runFixture({ enabled: ["afterglow"], operatorConfig: true, negativeOperator: true })
	assert.notEqual(result.status, 0, result.output)
	assert.ok(result.evidence.some(row => operatorTasks.includes(row.label) && row.become), result.output)
})

function selectedRefs(prefixes, digest = digestA) {
	return Object.fromEntries(prefixes.map(prefix => [`${prefix}_image_ref`, `fixture.invalid/${prefix}@${digest}`]))
}

function expectConsumers(result, service, refs) {
	assert.equal(result.status, 0, result.output)
	const rows = result.evidence.filter(row => row.label.startsWith(`${service}:`))
	assert.deepEqual(new Set(rows.map(row => row.host)), new Set(targetHosts), result.output)
	const names = components[service].map(prefix => `${prefix}_image_ref`)
	for (const row of rows) {
		assert.deepEqual(Object.fromEntries(Object.entries(row.refs).filter(([name]) => names.includes(name))), refs,
			`${row.host} ${row.label}\n${result.output}`)
	}
}

function expectSelection(result, refs) {
	assert.deepEqual(result.registryEvidence, [{ event: "selection" }, ...refs.map(ref => ({ event: "lookup", ref }))], result.output)
}

for (const channel of ["latest", "stable"]) {
	test(`serial consumers freeze ${channel} after registry movement and select fresh on the next native invocation`, () => {
		const prefixes = ["afterglow_backend", "afterglow_frontend"]
		const results = runFixture({ enabled: ["afterglow"], tags: "afterglow", serial: true,
			globals: { afterglow_image_tag: channel }, moveDigest: digestB, invocations: 2 })
		for (const [index, result] of results.entries()) {
			expectConsumers(result, "afterglow", selectedRefs(prefixes, index === 0 ? digestA : digestB))
			expectSelection(result, prefixes.map(prefix => `fixture.invalid/${prefix}:${channel}`))
			assert.equal(result.registryState.digest, digestB, result.output)
		}
	})
}

test("a descriptor failure after partial selection stops all serial role dispatch", () => {
	const result = runFixture({ enabled: ["afterglow", "lumen"], tags: "afterglow,lumen", serial: true,
		globals: { afterglow_image_tag: "latest", lumen_image_tag: "stable" },
		registry: { fail_refs: ["fixture.invalid/afterglow_frontend:latest"] } })
	assert.notEqual(result.status, 0, result.output)
	assert.match(result.output, /Cannot select exact afterglow images from the registry/)
	assert.deepEqual(result.evidence, [], result.output)
	expectSelection(result, ["fixture.invalid/afterglow_backend:latest", "fixture.invalid/afterglow_frontend:latest"])
})

test("--limit selects on its first target rather than the excluded global-first controller", () => {
	const result = runFixture({ enabled: ["afterglow"], tags: "afterglow", serial: true,
		globals: { afterglow_image_tag: "stable", enable_afterglow_frontend: false } })
	// The excluded/global-first host has an unusable Python interpreter. Selecting
	// there cannot succeed, even if propagation later hides the wrong coordinator.
	expectConsumers(result, "afterglow", selectedRefs(["afterglow_backend"]))
	expectSelection(result, ["fixture.invalid/afterglow_backend:stable"])
})

test("later-only enabled frontend uses the invocation's frozen image rather than a moved channel", () => {
	const result = runFixture({ enabled: ["afterglow"], tags: "afterglow", serial: true,
		globals: { afterglow_image_tag: "latest" },
		hostVars: { [targetHosts[0]]: { enable_afterglow_frontend: false },
			[targetHosts[1]]: { enable_afterglow_frontend: true } }, moveDigest: digestB })
	assert.equal(result.status, 0, result.output)
	for (const row of result.evidence.filter(row => row.label.startsWith("afterglow:"))) {
		assert.deepEqual(row.refs, selectedRefs(["afterglow_backend", ...(row.host === targetHosts[1] ? ["afterglow_frontend"] : [])]), result.output)
	}
	expectSelection(result, ["fixture.invalid/afterglow_backend:latest", "fixture.invalid/afterglow_frontend:latest"])
})

for (const workerHost of ["controller-a", "controller-c"]) {
	test(`three Palimpsest API targets freeze images with only ${workerHost} running a worker`, () => {
		const targets = ["controller-a", "controller-b", "controller-c"]
		const result = runFixture({ enabled: ["palimpsest"], tags: "palimpsest", serial: true, targets,
			globals: { palimpsest_image_tag: "latest" },
			hostVars: Object.fromEntries(targets.map(host => [host, { enable_palimpsest_hub_worker: host === workerHost }])),
			moveDigest: digestB })
		assert.equal(result.status, 0, result.output)
		const rows = result.evidence.filter(row => row.label.startsWith("palimpsest:"))
		assert.deepEqual(new Set(rows.map(row => row.host)), new Set(targets), result.output)
		for (const row of rows) {
			assert.deepEqual(row.refs, selectedRefs(["palimpsest_api", ...(row.host === workerHost ? ["palimpsest_worker"] : [])]), result.output)
		}
		expectSelection(result, ["fixture.invalid/palimpsest_api:latest", "fixture.invalid/palimpsest_worker:latest"])
		assert.equal(result.registryState.digest, digestB, result.output)
	})
}

for (const pin of ["rollback.invalid/worker:2.3.4", `rollback.invalid/worker@${digestB}`]) {
	test(`published-consumer inputs preserve later-only Palimpsest worker rollback ${pin}`, () => {
		const targets = ["controller-a", "controller-b", "controller-c"]
		const result = runFixture({ enabled: ["palimpsest"], tags: "palimpsest", serial: true, targets, productionDefaults: true,
			globals: { palimpsest_image_tag: "latest" },
			hostVars: Object.fromEntries(targets.map(host => [host, {
				enable_palimpsest_hub_worker: host === "controller-c",
				...(host === "controller-c" ? { palimpsest_worker_image_ref: pin } : {}),
			}])), registry: { fail_refs: ["fixture.invalid/palimpsest_worker:latest"] }, moveDigest: digestB })
		assert.equal(result.status, 0, result.output)
		const rows = result.evidence.filter(row => row.label.startsWith("palimpsest:"))
		assert.deepEqual(new Set(rows.map(row => row.host)), new Set(targets), result.output)
		for (const row of rows) assert.deepEqual(row.refs, {
			...selectedRefs(["palimpsest_api"]),
			...(row.host === "controller-c" ? { palimpsest_worker_image_ref: pin } : {}),
		}, result.output)
		expectSelection(result, ["fixture.invalid/palimpsest_api:latest"])
	})
}

for (const modeVars of [
	{ enable_palimpsest: "{{ inventory_hostname != 'controller-b' }}" },
	{ palimpsest_source_mode: "{{ inventory_hostname == 'controller-b' }}" },
	{ enable_palimpsest_source_build: "{{ inventory_hostname == 'controller-b' }}" },
	{ enable_source_build: "{{ inventory_hostname == 'controller-b' }}" },
	{ palimpsest_dev_mode: "{{ inventory_hostname == 'controller-b' }}" },
]) {
	test(`published-consumer inputs exclude worker on nonpublished target ${Object.keys(modeVars)[0]}`, () => {
		const result = runFixture({ enabled: ["palimpsest"], tags: "palimpsest", serial: true, productionDefaults: true,
			globals: { palimpsest_image_tag: "latest", ...modeVars },
			hostVars: { "controller-a": { enable_palimpsest_hub_worker: false },
				"controller-b": { enable_palimpsest_hub_worker: true } },
			registry: { fail_refs: ["fixture.invalid/palimpsest_worker:latest"] } })
		assert.equal(result.status, 0, result.output)
		for (const row of result.evidence.filter(row => row.label.startsWith("palimpsest:"))) {
			assert.deepEqual(row.refs, row.host === "controller-a" ? selectedRefs(["palimpsest_api"]) : {}, result.output)
		}
		expectSelection(result, ["fixture.invalid/palimpsest_api:latest"])
	})
}

for (const conflicting of [
	{ palimpsest_api_image_ref: "rollback.invalid/api:2.3.4" },
	{ palimpsest_api_image: "different.invalid/api" },
	{ palimpsest_image_tag: "stable" },
	{ palimpsest_image_namespace: "different.invalid", palimpsest_api_image: "{{ palimpsest_image_namespace }}/api" },
]) {
	test(`published-consumer inputs reject contradictory ${Object.keys(conflicting)[0]} before credentials and dispatch`, () => {
		const result = runFixture({ enabled: ["palimpsest"], tags: "palimpsest", serial: true, productionDefaults: true,
			globals: { enable_palimpsest_hub_worker: false,
				docker_registry_username: "{{ missing_registry_credential }}" },
			hostVars: { "controller-b": conflicting } })
		assert.notEqual(result.status, 0, result.output)
		assert.match(result.output, /Contradictory published image inputs for palimpsest_api_image_ref/)
		assert.deepEqual(result.registryEvidence, [], result.output)
		assert.deepEqual(result.evidence, [], result.output)
	})
}

test("published-consumer inputs retain later host namespace and tag with real Afterglow defaults", () => {
	const result = runFixture({ enabled: ["afterglow"], tags: "afterglow", serial: true, productionDefaults: true,
		hostVars: { "controller-a": { enable_afterglow_frontend: false },
			"controller-b": { enable_afterglow_frontend: true, afterglow_frontend_image: "{{ afterglow_image_namespace }}/frontend",
				afterglow_image_namespace: "rollback.invalid", afterglow_image_tag: "2.3.4",
				afterglow_backend_image_ref: "fixture.invalid/afterglow_backend:latest" } } })
	assert.equal(result.status, 0, result.output)
	for (const row of result.evidence.filter(row => row.label.startsWith("afterglow:"))) {
		assert.equal(row.refs.afterglow_backend_image_ref, selectedRefs(["afterglow_backend"]).afterglow_backend_image_ref, result.output)
		if (row.host === "controller-b") assert.equal(row.refs.afterglow_frontend_image_ref, "rollback.invalid/frontend:2.3.4", result.output)
	}
	expectSelection(result, ["fixture.invalid/afterglow_backend:latest"])
})

test("runtime-enabled Lumen controller shares the frozen selection across serial consumers", () => {
	const prefixes = ["lumen_api", "lumen_worker", "lumen_controller"]
	const result = runFixture({ enabled: ["lumen"], tags: "lumen", serial: true,
		globals: { lumen_image_tag: "latest", lumen_runtime_enabled: true }, moveDigest: digestB })
	expectConsumers(result, "lumen", selectedRefs(prefixes))
	expectSelection(result, prefixes.map(prefix => `fixture.invalid/${prefix}:latest`))
	assert.equal(result.registryState.digest, digestB, result.output)
})

test("later runtime-enabled Lumen controller shares the image selected before serial dispatch", () => {
	const result = runFixture({ enabled: ["lumen"], tags: "lumen", serial: true,
		hostVars: { [targetHosts[0]]: { lumen_runtime_enabled: false },
			[targetHosts[1]]: { lumen_runtime_enabled: true } }, moveDigest: digestB })
	assert.equal(result.status, 0, result.output)
	for (const row of result.evidence.filter(row => row.label.startsWith("lumen:"))) {
		assert.deepEqual(row.refs, selectedRefs(["lumen_api", "lumen_worker", ...(row.host === targetHosts[1] ? ["lumen_controller"] : [])]), result.output)
	}
	expectSelection(result, ["fixture.invalid/lumen_api:latest", "fixture.invalid/lumen_worker:latest", "fixture.invalid/lumen_controller:latest"])
})

for (const [service, sourceVars] of [
	["afterglow", { afterglow_source_mode: true }],
	["lumen", { enable_source_build: true }],
]) {
	test(`${service} source mode dispatches without selecting registry images`, () => {
		const result = runFixture({ enabled: [service], tags: service, serial: true,
			globals: { ...sourceVars, [`${service}_image_tag`]: "latest" },
			registry: { fail_refs: components[service].map(prefix => `fixture.invalid/${prefix}:latest`) } })
		expectConsumers(result, service, {})
		assert.deepEqual(result.registryEvidence, [], result.output)
	})
}

test("disabled components cannot participate in selection or propagate refs to consumers", () => {
	const active = {
		afterglow: ["afterglow_backend"], waygate: ["waygate_api"], drover: ["drover_api"],
		lumen: ["lumen_api"], palimpsest: ["palimpsest_api"],
	}
	const disabled = Object.values(components).flat().filter(prefix => !Object.values(active).flat().includes(prefix))
	const result = runFixture({ tags: services.join(","), serial: true, globals: {
		...Object.fromEntries(services.map(service => [`${service}_image_tag`, "latest"])),
		enable_afterglow_frontend: false, enable_afterglow_notion_worker: false,
		enable_waygate_worker: false, enable_drover_worker: false,
		enable_lumen_worker: false, lumen_runtime_enabled: true, enable_lumen_controller: false,
		enable_palimpsest_hub_worker: false,
	}, registry: { fail_refs: disabled.map(prefix => `fixture.invalid/${prefix}:latest`) } })
	for (const service of services) expectConsumers(result, service, selectedRefs(active[service]))
	assert.deepEqual(result.registryEvidence, services.flatMap(service => [
		{ event: "selection" }, ...active[service].map(prefix => ({ event: "lookup", ref: `fixture.invalid/${prefix}:latest` })),
	]), result.output)
})

test("immutable globals and CLI rollback overrides reach every consumer verbatim without registry access", () => {
	const refs = { afterglow_backend_image_ref: "rollback.invalid/backend:1.2.3",
		afterglow_frontend_image_ref: `rollback.invalid/frontend@${digestB}` }
	const result = runFixture({ enabled: ["afterglow"], tags: "afterglow", serial: true,
		globals: { afterglow_image_tag: "latest", afterglow_backend_image_ref: "ignored.invalid/backend:latest",
			afterglow_frontend_image_ref: refs.afterglow_frontend_image_ref },
		extraVars: { afterglow_backend_image_ref: refs.afterglow_backend_image_ref } })
	expectConsumers(result, "afterglow", refs)
	assert.deepEqual(result.registryEvidence, [], result.output)
})

test("mixed selection preserves immutable overrides while freezing the moving component", () => {
	const refs = { afterglow_backend_image_ref: "rollback.invalid/backend:1.2.3",
		afterglow_worker_image_ref: `rollback.invalid/worker@${digestB}`,
		...selectedRefs(["afterglow_frontend"]) }
	const result = runFixture({ enabled: ["afterglow"], tags: "afterglow", serial: true,
		globals: { afterglow_image_tag: "latest", enable_afterglow_notion_worker: true,
			afterglow_backend_image_ref: refs.afterglow_backend_image_ref, afterglow_worker_image_ref: refs.afterglow_worker_image_ref },
		moveDigest: digestB })
	expectConsumers(result, "afterglow", refs)
	expectSelection(result, ["fixture.invalid/afterglow_frontend:latest"])
	assert.equal(result.registryState.digest, digestB, result.output)
})

for (const suffix of [":latest", ":stable", ""]) {
	test(`native -e moving image_ref${suffix || " (implicit latest)"} cannot outrank the selected digest and dispatch`, () => {
		const ref = `fixture.invalid/afterglow_backend${suffix}`
		const result = runFixture({ enabled: ["afterglow"], tags: "afterglow", serial: true,
			globals: { afterglow_frontend_image_ref: "fixture.invalid/frontend:1.2.3" },
			extraVars: { afterglow_backend_image_ref: ref } })
		assert.notEqual(result.status, 0, result.output)
		assert.match(result.output, /afterglow_backend_image_ref overrides this invocation's selected image reference/)
		assert.deepEqual(result.evidence, [], result.output)
		expectSelection(result, [ref])
	})
}

test("moving image_ref from native globals.d also fails closed before role dispatch", () => {
	const ref = "fixture.invalid/afterglow_backend:latest"
	const result = runFixture({ enabled: ["afterglow"], tags: "afterglow", serial: true,
		globals: { afterglow_backend_image_ref: ref, afterglow_frontend_image_ref: "fixture.invalid/frontend:1.2.3" } })
	assert.notEqual(result.status, 0, result.output)
	assert.match(result.output, /afterglow_backend_image_ref overrides this invocation's selected image reference/)
	assert.deepEqual(result.evidence, [], result.output)
	expectSelection(result, [ref])
})

for (const [firstTargetMode, modeVars] of [
	["disabled", { enable_waygate: "{{ inventory_hostname == 'controller-b' }}" }],
	["source-mode", { waygate_source_mode: "{{ inventory_hostname == 'controller-a' }}" }],
]) {
	test(`previous service selection cannot authorize a published consumer with a ${firstTargetMode} first target`, () => {
		const result = runFixture({ enabled: ["afterglow", "waygate"], tags: "afterglow,waygate", serial: true,
			globals: { afterglow_image_tag: "latest", waygate_image_tag: "latest", ...modeVars } })
		assert.notEqual(result.status, 0, result.output)
		assert.deepEqual(result.evidence.filter(row => row.label.startsWith("waygate:") && row.host === targetHosts[1]), [], result.output)
		expectSelection(result, ["fixture.invalid/afterglow_backend:latest", "fixture.invalid/afterglow_frontend:latest"])
	})
}

for (const [scenario, vars, expected] of [
	["configured public URL", { palimpsest_public_endpoint_url: "https://hub.example.test" }, "https://hub.example.test"],
	["separate trusted BFF URL", { palimpsest_public_endpoint_url: "https://hub.example.test",
		afterglow_service_palimpsest_internal_url: "https://private.example.test/v1" }, "https://private.example.test/v1"],
	["unset public URL with public routing enabled", { palimpsest_public_haproxy_enabled: true }, undefined],
	["explicit empty override", { palimpsest_public_endpoint_url: "https://hub.example.test",
		afterglow_service_palimpsest_internal_url: "" }, undefined],
	["integration disabled", { afterglow_service_palimpsest_enabled: false,
		afterglow_service_palimpsest_internal_url: "http://unused.example.test" }, undefined],
]) {
	test(`Palimpsest ${scenario} preserves effective TOML precedence`, () => {
		const result = runPalimpsestEndpointFixture(vars)
		assert.equal(result.status, 0, result.output)
		for (const layer of ["afterglow.conf", "afterglow.kolla.conf"]) {
			assert.equal(result.rendered[layer].palimpsest_internal_url, expected)
		}
		assert.equal(result.rendered.effective.palimpsest_internal_url, expected ?? "https://operator.example.test")
	})
}

for (const url of ["http://hub.example.test", "https:///hub", "https://user:password@hub.example.test",
	"https://hub.example.test?token=fixture", "https://hub.example.test#fragment"]) {
	test(`Palimpsest native genconfig rejects ${url} before emitting configuration`, () => {
		const result = runPalimpsestEndpointFixture({ afterglow_service_palimpsest_internal_url: url })
		assert.notEqual(result.status, 0, result.output)
		assert.match(result.output, /must be a trusted HTTPS endpoint/)
		assert.deepEqual(result.rendered, {})
		assert.deepEqual(result.emitted, [], result.output)
	})
}

test("Palimpsest native genconfig validates a later host's endpoint before emitting configuration", () => {
	const result = runPalimpsestEndpointFixture({}, {
		"controller-a": "https://hub.example.test",
		"controller-b": "http://insecure.example.test",
	})
	assert.notEqual(result.status, 0, result.output)
	assert.match(result.output, /must be a trusted HTTPS endpoint/)
	assert.deepEqual(result.emitted_by_host["controller-b"], [], result.output)
	assert.deepEqual(result.emitted_by_host["controller-a"], ["afterglow.conf", "afterglow.kolla.conf"], result.output)
	assert.equal(result.rendered["afterglow.kolla.conf"].palimpsest_internal_url, "https://hub.example.test")
})
