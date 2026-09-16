const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const os = require("node:os")
const { spawnSync } = require("node:child_process")
const test = require("node:test")

const root = path.resolve(__dirname, "..")
const runtime = path.join(root, "deploy/kolla/operator/.venv/bin")
const services = ["afterglow", "waygate", "drover", "lumen", "palimpsest"]
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
                    'action': task_vars.get('kolla_action')}
        with open(os.environ['RUNTIME_EVIDENCE'], 'a') as output:
            output.write(json.dumps(evidence) + '\\n')
        expected = self._task.args.get('expected_become', True)
        if evidence['become'] != expected:
            return {'failed': True, 'msg': ('Missing inherited become: ' if expected else 'Unexpected operator become: ') + label}
        return {'changed': False, 'stat': {'exists': True, 'isreg': True, 'readable': True}}
`

function runFixture({ enabled = services, tags, negative = false, standalone = false, operatorConfig = false, negativeOperator = false } = {}) {
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
		write("multinode", ["[all]", "controller ansible_connection=local", "delegate ansible_connection=local",
			...services.flatMap(name => [`[${name}]`, "controller"]), "[loadbalancer]", "controller", "[deployment]", "delegate", ""].join("\n"))
		write("globals.yml", JSON.stringify({
			...Object.fromEntries(services.map(name => [`enable_${name}`, false])),
			ansible_facts: { runtime_fixture: true },
			enable_haproxy: true, runtime_config_marker: "base",
			kolla_ansible_setup_filter: [], kolla_ansible_setup_gather_subset: ["!all"],
		}))
		write("passwords.yml", "{}\n")
		write("globals.d/10-services.yml", JSON.stringify({
			...Object.fromEntries(enabled.map(name => [`enable_${name}`, true])),
			runtime_config_marker: "globals.d-loaded",
		}))
		write("ansible.cfg", "[defaults]\nforks=1\nretry_files_enabled=False\nhost_key_checking=False\n")
		write("action_plugins/runtime_probe.py", action)
		const probe = (label, delegated = false) => `- name: Probe ${label}\n  runtime_probe:\n    label: ${label}\n${delegated ? "  delegate_to: delegate\n" : ""}`
		for (const name of enabled) {
			write(`ansible/roles/${name}/tasks/main.yml`, "- ansible.builtin.import_tasks: deploy.yml\n")
			write(`ansible/roles/${name}/tasks/deploy.yml`, probe(`${name}:deploy`) + probe(`${name}:delegated`, true))
			write(`ansible/roles/${name}/tasks/loadbalancer.yml`, probe(`${name}:haproxy`))
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
sys.argv = ['kolla-ansible', 'deploy', '-i', 'multinode'] + sys.argv[1:]
from kolla_ansible.cmd.kolla_ansible import main
sys.exit(main())
`)
		// Isolate from operator credentials, inventories, callbacks and become overrides.
		const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith("ANSIBLE_") && !key.startsWith("KOLLA_")))
		const result = spawnSync(path.join(runtime, "python"), ["invoke.py", ...(tags ? ["--tags", tags] : [])], {
			cwd: dir, encoding: "utf8", timeout: 90000, maxBuffer: 4 * 1024 * 1024,
			env: { ...env, PATH: `${runtime}${path.delimiter}${process.env.PATH}`, KOLLA_CONFIG_PATH: dir,
				ANSIBLE_CONFIG: path.join(dir, "ansible.cfg"), ANSIBLE_LOCAL_TEMP: path.join(dir, "tmp"),
				ANSIBLE_ACTION_PLUGINS: path.join(dir, "action_plugins"),
				ANSIBLE_ROLES_PATH: path.join(dir, "ansible/roles"),
				OBJC_DISABLE_INITIALIZE_FORK_SAFETY: "YES", RUNTIME_EVIDENCE: path.join(dir, "evidence.jsonl") },
		})
		const evidence = fs.existsSync(path.join(dir, "evidence.jsonl"))
			? fs.readFileSync(path.join(dir, "evidence.jsonl"), "utf8").trim().split("\n").map(JSON.parse) : []
		return { ...result, evidence, output: `${result.stdout}\n${result.stderr}\n${result.error || ""}` }
	} finally {
		fs.rmSync(dir, { recursive: true, force: true })
	}
}

function expectSuccess(result, selected, haproxy = true) {
	assert.equal(result.status, 0, result.output)
	const expected = selected.flatMap(name => [`${name}:deploy`, `${name}:delegated`, ...(haproxy ? [`${name}:haproxy`] : [])])
	if (haproxy) expected.push("haproxy:config", "haproxy:reconcile")
	assert.deepEqual(result.evidence.map(row => row.label).sort(), expected.sort(), result.output)
	for (const row of result.evidence) {
		assert.equal(row.become, true, row.label)
		assert.equal(row.config, "globals.d-loaded", row.label)
		assert.equal(row.action, "deploy", row.label)
		if (row.label.endsWith(":delegated")) assert.equal(row.delegate, "delegate")
	}
}

test("native kolla-ansible deploy -i multinode inherits privilege through every service and HAProxy", () => {
	expectSuccess(runFixture(), services)
})

test("native Kolla optional service tags isolate runtime execution", () => {
	expectSuccess(runFixture({ tags: "afterglow,lumen" }), ["afterglow", "lumen"])
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
