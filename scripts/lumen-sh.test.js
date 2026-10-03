const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")
const { spawnSync } = require("node:child_process")

const installer = fs.readFileSync(path.resolve(__dirname, "../frontend/static/install/lumen.sh"), "utf8")
const bases = ["https://gateway.example.com/responses/v1", "https://gateway.example.com/anthropic"]
const secret = "sk-lumen-private-'$`quoted`-full-key"
const responsesModel = "responses/model-2026"
const anthropicModel = "anthropic/model-2026"
const commandEnv = {}
for (const name of ["PATH", "LANG", "LC_ALL", "TERM"]) {
	if (process.env[name] !== undefined) commandEnv[name] = process.env[name]
}

// A real controlling terminal is separate from the pipe carrying the script.
// Python's stdlib works on both supported OSes, unlike platform-specific script(1).
const ptyDriver = String.raw`
import errno, fcntl, json, os, pty, select, signal, subprocess, sys, termios, time
request = json.load(sys.stdin)
master, slave = pty.openpty()
status_read, status_write = os.pipe()
release_read, release_write = os.pipe()
# macOS revokes the tty when its session leader exits. Keep a shell-like
# session owner alive, with the installer as a normal child, until the owner
# checks its ORIGINAL tty descriptor and reports settings on a separate pipe.
owner_source = '''
import json, os, signal, subprocess, sys, termios
original = termios.tcgetattr(1)
child = subprocess.Popen(json.loads(sys.argv[1]))
def forward(sig, frame):
    if child.poll() is None:
        child.send_signal(sig)
for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGTSTP):
    signal.signal(sig, forward)
status = child.wait()
os.write(int(sys.argv[2]), json.dumps({'status': status,
    'echoRestored': termios.tcgetattr(1) == original}).encode())
os.read(int(sys.argv[3]), 1)
'''
def session():
    os.setsid()
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
child = subprocess.Popen(['python3', '-c', owner_source, json.dumps(request['command']),
                          str(status_write), str(release_read)],
                         stdin=subprocess.PIPE, stdout=slave, stderr=slave,
                         env=request['env'], preexec_fn=session,
                         pass_fds=(status_write, release_read))
os.close(status_write)
os.close(release_read)
output = bytearray()
index = 0
key_echo = None
completion = None
try:
    child.stdin.write(request['script'].encode())
    child.stdin.close()
    deadline = time.monotonic() + 12
    while completion is None:
        ready, _, _ = select.select([master, status_read], [], [], 0.05)
        if master in ready:
            output.extend(os.read(master, 65536))
        if index < len(request['actions']):
            action = request['actions'][index]
            if action['prompt'].encode() in output:
                if action['prompt'] == 'Lumen API key: ':
                    key_echo = bool(termios.tcgetattr(slave)[3] & termios.ECHO)
                if 'signal' in action:
                    if action.get('partial'):
                        os.write(master, action['partial'].encode())
                    os.kill(child.pid, getattr(signal, action['signal']))
                else:
                    os.write(master, action['value'].encode() + b'\n')
                index += 1
        if status_read in ready:
            completion = json.loads(os.read(status_read, 4096))
        if time.monotonic() > deadline:
            raise TimeoutError('PTY interaction timed out: ' + output.decode(errors='replace'))
    while select.select([master], [], [], 0)[0]:
        output.extend(os.read(master, 65536))
    result = {**completion, 'output': output.decode('utf-8', errors='replace'),
              'keyEcho': key_echo, 'answered': index, 'failure': None}
    os.write(release_write, b'1')
    child.wait(timeout=2)
finally:
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()
    for fd in (master, slave, status_read, release_write):
        os.close(fd)
print(json.dumps(result))
`

function fixture(t, config = "") {
	const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "lumen-sh-")))
	t.after(() => fs.rmSync(root, { recursive: true, force: true }))
	const home = path.join(root, "home ' spaced")
	const codexHome = path.join(home, "custom-codex")
	const zdotdir = path.join(home, "custom-zsh")
	const xdg = path.join(home, "custom-config")
	for (const dir of [home, codexHome, zdotdir, xdg]) fs.mkdirSync(dir, { mode: 0o700 })
	const profile = path.join(home, ".bash_profile")
	const bashrc = path.join(home, ".bashrc")
	const zshrc = path.join(zdotdir, ".zshrc")
	fs.writeFileSync(profile, "export EXISTING_LOGIN=preserved\n", { mode: 0o640 })
	fs.writeFileSync(bashrc, "export EXISTING_BASH=preserved\n", { mode: 0o644 })
	fs.writeFileSync(zshrc, "export EXISTING_ZSH=preserved\n", { mode: 0o644 })
	const configPath = path.join(codexHome, "config.toml")
	fs.writeFileSync(configPath, config, { mode: 0o640 })
	const env = { ...commandEnv, HOME: home, CODEX_HOME: codexHome, ZDOTDIR: zdotdir, XDG_CONFIG_HOME: xdg }
	return { root, home, codexHome, zdotdir, xdg, profile, bashrc, zshrc, configPath,
		keyPath: path.join(xdg, "lumen", "key.sh"), env }
}

function actions(optIn = "n", model = responsesModel) {
	return [
		{ prompt: "Lumen API key: ", value: secret },
		{ prompt: "Codex Responses model ID: ", value: model },
		{ prompt: "Anthropic model ID: ", value: anthropicModel },
		{ prompt: "Replace the default Codex model? [y/N]: ", value: optIn },
	]
}

function install(f, options = {}) {
	const request = {
		command: ["sh", ...(options.trace ? ["-x", "-v"] : []), "-s", "--", ...(options.bases ?? bases)],
		env: f.env,
		script: installer,
		actions: options.actions ?? actions(options.optIn),
	}
	const result = spawnSync("python3", ["-c", ptyDriver], {
		input: JSON.stringify(request), env: f.env, encoding: "utf8", timeout: 20000, maxBuffer: 1024 * 1024,
	})
	assert.equal(result.error, undefined)
	assert.equal(result.status, 0, result.stderr)
	const interaction = JSON.parse(result.stdout)
	assert.equal(interaction.failure, null, interaction.output)
	return interaction
}

function withoutTerminal(f, urls = bases) {
	const result = spawnSync("sh", ["-s", "--", ...urls], {
		input: installer, encoding: "utf8", env: f.env, detached: true, timeout: 5000,
	})
	assert.equal(result.error, undefined)
	return { status: result.status, output: result.stdout + result.stderr }
}

function snapshot(root) {
	const found = {}
	function walk(dir) {
		for (const name of fs.readdirSync(dir).sort()) {
			const full = path.join(dir, name)
			const info = fs.lstatSync(full)
			found[path.relative(root, full)] = {
				mode: info.mode & 0o777,
				content: info.isFile() ? fs.readFileSync(full, "utf8") : info.isSymbolicLink() ? fs.readlinkSync(full) : null,
			}
			if (info.isDirectory()) walk(full)
		}
	}
	walk(root)
	return found
}

function parseConfig(f) {
	const result = spawnSync("python3", ["-c", "import json,sys,tomllib; print(json.dumps(tomllib.load(open(sys.argv[1], 'rb'))))", f.configPath], { env: f.env, encoding: "utf8" })
	assert.equal(result.status, 0, result.stderr)
	return JSON.parse(result.stdout)
}

function newShell(f, shell, traced = false) {
	const probe = "python3 -c 'import json,os; print(json.dumps(dict(os.environ)))'"
	const args = shell === "bash" ? ["--noprofile", ...(traced ? ["-xv"] : []), "-ic", probe] : ["-d", "-ic", probe]
	const result = spawnSync(shell, args, { env: f.env, encoding: "utf8", timeout: 5000 })
	assert.equal(result.error, undefined)
	assert.equal(result.status, 0, result.stderr)
	assert.ok(!result.stderr.includes(secret), "profile loading must not trace the private key")
	return JSON.parse(result.stdout)
}

function assertEnv(env, f) {
	assert.equal(env.LUMEN_API_KEY, secret)
	assert.equal(env.ANTHROPIC_AUTH_TOKEN, secret)
	assert.equal(env.ANTHROPIC_API_KEY, undefined, "stale direct-provider key must not reach Claude")
	assert.equal(env.LUMEN_MODEL, anthropicModel)
	assert.equal(env.ANTHROPIC_BASE_URL, bases[1])
	for (const name of ["ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL"]) {
		assert.equal(env[name], anthropicModel)
	}
	assert.equal(env.CODEX_HOME, f.codexHome)
	assert.equal(env.LUMEN_CODEX_MODEL, responsesModel)
	assert.ok(fs.statSync(env.CODEX_CA_CERTIFICATE).isFile())
}

const existingConfig = `# User-owned defaults
model = "keep-default"
model_provider = "openai"
model_reasoning_effort = "high"
instructions = """
[model_providers.lumen]
model = "not-a-real-setting"
"""
[features]
web_search_request = true
[model_providers."lumen"]
name = "Old name"
base_url = "https://old.example.com/v1"
env_key = "OLD_KEY"
wire_api = "chat"
request_max_retries = 7
[model_providers.lumen.http_headers]
"X-Lumen-Provider" = "provider-choice"
[model_providers.other]
name = "Keep this provider"
base_url = "https://other.example.com/v1"
[mcp_servers.custom]
command = "my-server"
args = [
  "one", "two",
]
`

test("piped script installs private credentials, preserves TOML and profile modes, and loads a fresh bash shell", (t) => {
	const f = fixture(t, existingConfig)
	f.env.ANTHROPIC_API_KEY = "sk-synthetic-stale-direct-provider-key"
	const result = install(f, { trace: true })
	assert.equal(result.status, 0, result.output)
	assert.equal(result.keyEcho, false)
	assert.equal(result.echoRestored, true)
	assert.ok(!result.output.includes(secret))
	assert.ok(result.output.includes(`codex --strict-config -c model_provider=lumen -m ${responsesModel}\r\n`))
	const config = parseConfig(f)
	assert.equal(config.model, "keep-default")
	assert.equal(config.model_provider, "openai")
	assert.equal(config.model_reasoning_effort, "high")
	assert.equal(config.features.web_search_request, true)
	assert.deepEqual(config.mcp_servers.custom.args, ["one", "two"])
	assert.ok(config.instructions.includes('model = "not-a-real-setting"'))
	assert.equal(config.model_providers.other.name, "Keep this provider")
	assert.deepEqual(config.model_providers.lumen, {
		name: "Lumen Responses", base_url: bases[0], env_key: "LUMEN_API_KEY", wire_api: "responses",
		requires_openai_auth: false, supports_websockets: false, request_max_retries: 7,
		http_headers: { "X-Lumen-Provider": "provider-choice" },
	})
	for (const file of [f.profile, f.bashrc, f.zshrc, f.configPath]) assert.ok(!fs.readFileSync(file, "utf8").includes(secret))
	assert.equal(fs.statSync(f.profile).mode & 0o777, 0o640)
	assert.equal(fs.statSync(f.bashrc).mode & 0o777, 0o644)
	assert.equal(fs.statSync(f.zshrc).mode & 0o777, 0o644)
	assert.equal(fs.statSync(f.configPath).mode & 0o777, 0o600)
	assert.equal(fs.statSync(f.keyPath).mode & 0o777, 0o600)
	assert.equal(fs.statSync(path.dirname(f.keyPath)).mode & 0o777, 0o700)
	assert.equal(fs.statSync(f.codexHome).mode & 0o777, 0o700)
	const loaded = newShell(f, "bash", true)
	assertEnv(loaded, f)
	assert.equal(loaded.EXISTING_BASH, "preserved")
	const backup = fs.readdirSync(f.codexHome).find((name) => name.includes(".lumen-backup-"))
	assert.equal(fs.readFileSync(path.join(f.codexHome, backup), "utf8"), existingConfig)
	assert.equal(fs.statSync(path.join(f.codexHome, backup)).mode & 0o777, 0o600)
	const first = snapshot(f.home)
	// Rerun from the newly configured shell, not the unconfigured fixture.
	// Its inherited system CA must not create a new Node CA override/block.
	f.env = loaded
	const second = install(f)
	assert.equal(second.status, 0, second.output)
	assert.deepEqual(snapshot(f.home), first, "rerun must not add blocks or backups or change content/modes")
	const rotatedSecret = "sk-synthetic-rotated-key"
	const rotatedModel = "responses/rotated-model"
	const rotation = actions("n", rotatedModel)
	rotation[0].value = rotatedSecret
	const rotated = install(f, { actions: rotation })
	assert.equal(rotated.status, 0, rotated.output)
	assert.ok(!rotated.output.includes(secret) && !rotated.output.includes(rotatedSecret))
	const reloaded = newShell(f, "bash")
	assert.equal(reloaded.LUMEN_API_KEY, rotatedSecret)
	assert.equal(reloaded.ANTHROPIC_AUTH_TOKEN, rotatedSecret)
	assert.equal(reloaded.LUMEN_CODEX_MODEL, rotatedModel)
	assert.equal(reloaded.ANTHROPIC_API_KEY, undefined)
	assert.equal(parseConfig(f).model, "keep-default")
	for (const [name, value] of Object.entries(snapshot(f.home))) {
		if (path.join(f.home, name) === f.keyPath || value.content === null) continue
		assert.ok(!value.content.includes(secret) && !value.content.includes(rotatedSecret),
			"keys must not appear in any profile, config, backup, or leftover staging file")
	}
})

test("fresh zsh session resolves the private key and model environment", (t) => {
	const availability = spawnSync("zsh", ["--version"], { env: commandEnv, encoding: "utf8" })
	if (availability.error?.code === "ENOENT") return t.skip("zsh is not installed")
	const f = fixture(t)
	assert.equal(install(f).status, 0)
	const loaded = newShell(f, "zsh")
	assertEnv(loaded, f)
	assert.equal(loaded.EXISTING_ZSH, "preserved")
})

test("opt-in changes only the top-level model and prints the short command", (t) => {
	const f = fixture(t, existingConfig)
	const result = install(f, { optIn: "yes" })
	assert.equal(result.status, 0, result.output)
	const config = parseConfig(f)
	assert.equal(config.model, responsesModel)
	assert.equal(config.model_provider, "openai")
	assert.equal(config.model_providers.lumen.http_headers["X-Lumen-Provider"], "provider-choice")
	assert.ok(result.output.includes("codex --strict-config -c model_provider=lumen\r\n"))
	assert.ok(!result.output.includes(" -m "))
})

test("omitted URLs prompt through /dev/tty and default-model opt-in handles a file without a final newline", (t) => {
	const f = fixture(t, 'model_provider = "openai"')
	const result = install(f, { bases: [], actions: [
		{ prompt: "Codex HTTPS base URL: ", value: bases[0] },
		{ prompt: "Anthropic HTTPS base URL: ", value: bases[1] }, ...actions("y"),
	] })
	assert.equal(result.status, 0, result.output)
	assert.equal(result.answered, 6)
	assert.equal(parseConfig(f).model, responsesModel)
	assertEnv(newShell(f, "bash"), f)
})

test("inline and dotted provider settings retain nested tables and unrelated values", (t) => {
	for (const config of [
		'model_providers = { lumen = { name = "old", http_headers = { "X-Lumen-Provider" = "chosen" } }, other = { name = "Keep" } }\n',
		'[model_providers]\nlumen = { name = "old", http_headers = { "X-Lumen-Provider" = "chosen" } }\nother = { name = "Keep" }\n',
		'model_providers.lumen.name = "old"\n[model_providers.lumen.http_headers]\n"X-Lumen-Provider" = "chosen"\n[model_providers.other]\nname = "Keep"\n',
	]) {
		const f = fixture(t, config)
		const result = install(f)
		assert.equal(result.status, 0, result.output)
		const parsed = parseConfig(f)
		assert.equal(parsed.model_providers.lumen.base_url, bases[0])
		assert.equal(parsed.model_providers.lumen.http_headers["X-Lumen-Provider"], "chosen")
		assert.equal(parsed.model_providers.other.name, "Keep")
		assert.equal(parsed.model, undefined)
	}
})

test("unsafe URLs and wrong invocation arity reject without echoing inputs or mutating files", (t) => {
	const f = fixture(t, existingConfig)
	const before = snapshot(f.home)
	for (const value of [
		"http://gateway.example.com/v1", "https://user:secret@gateway.example.com/v1",
		"https://gateway.example.com/v1?token=private", "https://gateway.example.com/v1#private",
		"https://gateway.example.com/v1?", "https://gateway.example.com/v1#",
		"https://bad_host/v1", "https://gateway.example.com:/v1",
		"https://gateway.example.com/\nprivate", "https://gateway.example.com/%0a",
		"https://gateway.example.com:99999/v1", "https://gateway.example.com/$(touch-private)",
	]) {
		const result = install(f, { bases: [value, bases[1]], actions: [] })
		assert.equal(result.status, 1)
		assert.ok(result.output.includes("Invalid HTTPS endpoint."), "must reject URL, not fail later for lack of tty")
		assert.equal(result.answered, 0)
		assert.ok(!result.output.includes(value))
		assert.ok(!result.output.includes("private"))
		assert.deepEqual(snapshot(f.home), before)
	}
	for (const urls of [[bases[0]], [...bases, "unexpected"]]) {
		assert.equal(install(f, { bases: urls, actions: [] }).status, 1)
		assert.deepEqual(snapshot(f.home), before)
	}
})

test("discovery-advertised private and intranet HTTPS endpoints configure without network access", (t) => {
	for (const urls of [
		["https://10.0.0.1:8443/responses/v1", "https://service.internal/anthropic"],
		["https://[::1]:8443/responses/v1", "https://localhost/anthropic"],
		["https://intranet/responses/v1", "https://gateway.local/anthropic"],
	]) {
		const f = fixture(t)
		const result = install(f, { bases: urls })
		assert.equal(result.status, 0, result.output)
		assert.equal(parseConfig(f).model_providers.lumen.base_url, urls[0])
		assert.equal(newShell(f, "bash").ANTHROPIC_BASE_URL, urls[1])
	}
})

test("nonTTY failure does not consume stdin as a credential or modify profiles", (t) => {
	const f = fixture(t, existingConfig)
	const before = snapshot(f.home)
	for (const urls of [bases, []]) {
		const result = withoutTerminal(f, urls)
		assert.equal(result.status, 1)
		assert.ok(result.output.includes("A controlling terminal is required."))
		assert.ok(!result.output.includes(secret))
		assert.deepEqual(snapshot(f.home), before)
	}
})

test("invalid model and opt-in inputs restore echo and leave every target unchanged", (t) => {
	for (const invalid of ["bad model", "$(touch bad)", "-leading-option", "bad\tmodel", "a".repeat(201)]) {
		const f = fixture(t, existingConfig)
		const before = snapshot(f.home)
		const result = install(f, { actions: actions("n", invalid).slice(0, 2) })
		assert.equal(result.status, 1)
		assert.ok(result.output.includes("Invalid model ID."))
		assert.equal(result.echoRestored, true)
		assert.ok(!result.output.includes(secret))
		assert.deepEqual(snapshot(f.home), before)
	}
	const f = fixture(t)
	const before = snapshot(f.home)
	assert.equal(install(f, { optIn: "maybe" }).status, 1)
	assert.deepEqual(snapshot(f.home), before)
})

test("catchable termination signals restore echo during the secret prompt", (t) => {
	for (const sig of ["SIGINT", "SIGTERM", "SIGHUP", "SIGQUIT", "SIGTSTP"]) {
		const f = fixture(t, existingConfig)
		const before = snapshot(f.home)
		const result = install(f, { actions: [{ prompt: "Lumen API key: ", partial: secret, signal: sig }] })
		assert.equal(result.status, 1, result.output)
		assert.equal(result.keyEcho, false)
		assert.equal(result.echoRestored, true)
		assert.ok(!result.output.includes(secret))
		assert.deepEqual(snapshot(f.home), before)
	}
})

test("symlink, hardlink, special-file, and malformed TOML hazards fail without touching their targets", (t) => {
	for (const hazard of ["profile", "config", "parent", "key", "hardlink", "directory", "toml", "markers"]) {
		const f = fixture(t, existingConfig)
		const outside = path.join(f.root, "outside")
		fs.writeFileSync(outside, "untouched external data\n")
		if (hazard === "profile" || hazard === "config") {
			const target = hazard === "profile" ? f.profile : f.configPath
			fs.unlinkSync(target)
			fs.symlinkSync(outside, target)
		} else if (hazard === "parent") {
			fs.rmSync(f.codexHome, { recursive: true })
			const external = path.join(f.root, "external-codex")
			fs.mkdirSync(external)
			fs.writeFileSync(path.join(external, "config.toml"), existingConfig)
			fs.symlinkSync(external, f.codexHome)
		} else if (hazard === "key") {
			fs.mkdirSync(path.dirname(f.keyPath), { mode: 0o700 })
			fs.symlinkSync(outside, f.keyPath)
		} else if (hazard === "hardlink") {
			fs.unlinkSync(f.profile)
			fs.linkSync(outside, f.profile)
		} else if (hazard === "directory") {
			fs.unlinkSync(f.profile)
			fs.mkdirSync(f.profile)
		} else if (hazard === "toml") {
			fs.writeFileSync(f.configPath, "model = [broken\n")
		} else {
			fs.appendFileSync(f.bashrc, "# >>> Lumen CLI >>>\nunterminated\n")
		}
		const before = snapshot(f.root)
		const result = install(f, { actions: [] })
		assert.equal(result.status, 1, result.output)
		assert.ok(!result.output.includes(secret))
		assert.deepEqual(snapshot(f.root), before, hazard)
	}
})

test("bash login profile selection does not overwrite lower-precedence profiles", (t) => {
	const f = fixture(t)
	fs.unlinkSync(f.profile)
	const login = path.join(f.home, ".bash_login")
	const fallback = path.join(f.home, ".profile")
	fs.writeFileSync(login, "export LOGIN_CHOICE=preserved\n", { mode: 0o644 })
	fs.writeFileSync(fallback, "export FALLBACK=untouched\n", { mode: 0o644 })
	assert.equal(install(f).status, 0)
	assert.equal(fs.readFileSync(fallback, "utf8"), "export FALLBACK=untouched\n")
	const probe = spawnSync("bash", ["--noprofile", "-c", '. "$HOME/.bash_login"; python3 -c \'import json,os; print(json.dumps(dict(os.environ)))\''], { env: f.env, encoding: "utf8" })
	assert.equal(probe.status, 0, probe.stderr)
	const env = JSON.parse(probe.stdout)
	assertEnv(env, f)
	assert.equal(env.LOGIN_CHOICE, "preserved")
})

test("explicit trusted CA bundle is validated and exported to both CLIs; invalid bundles fail safely", (t) => {
	const f = fixture(t)
	const system = process.platform === "darwin" ? "/private/etc/ssl/cert.pem" : "/etc/ssl/certs/ca-certificates.crt"
	const bundle = path.join(f.home, "trusted.pem")
	fs.copyFileSync(system, bundle)
	const linkedBundle = path.join(f.home, "trusted-link.pem")
	fs.symlinkSync(bundle, linkedBundle)
	// Existing enterprise/user CA wins over system defaults, but not an
	// explicit LUMEN_CA_BUNDLE. Both paths are persisted in fresh shells.
	f.env.CODEX_CA_CERTIFICATE = linkedBundle
	assert.equal(install(f).status, 0)
	assert.equal(newShell(f, "bash").CODEX_CA_CERTIFICATE, linkedBundle)
	const inherited = newShell(f, "bash")
	assert.equal(inherited.NODE_EXTRA_CA_CERTS, linkedBundle)
	const customSnapshot = snapshot(f.home)
	f.env = inherited
	assert.equal(install(f).status, 0)
	assert.deepEqual(snapshot(f.home), customSnapshot, "inherited custom CA must not change profiles or create backups")
	const override = path.join(f.home, "override.pem")
	fs.copyFileSync(system, override)
	const linkedOverride = path.join(f.home, "override-link.pem")
	fs.symlinkSync(override, linkedOverride)
	f.env.LUMEN_CA_BUNDLE = linkedOverride
	const result = install(f)
	assert.equal(result.status, 0, result.output)
	const loaded = newShell(f, "bash")
	assert.equal(loaded.CODEX_CA_CERTIFICATE, linkedOverride)
	assert.equal(loaded.NODE_EXTRA_CA_CERTS, linkedOverride)
	f.env = { ...loaded }
	delete f.env.LUMEN_CA_BUNDLE
	const overrideSnapshot = snapshot(f.home)
	assert.equal(install(f).status, 0)
	assert.deepEqual(snapshot(f.home), overrideSnapshot, "explicit CA must stay shared after opening a new shell")
	fs.writeFileSync(override, "not a PEM certificate")
	const before = snapshot(f.home)
	const rejected = install(f, { actions: [] })
	assert.equal(rejected.status, 1)
	assert.deepEqual(snapshot(f.home), before)
})
