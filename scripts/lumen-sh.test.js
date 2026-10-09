const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")
const { spawn, spawnSync } = require("node:child_process")
const https = require("node:https")

const installer = fs.readFileSync(path.resolve(__dirname, "../frontend/static/install/lumen.sh"), "utf8")
let bases
let tlsServer
let tlsRoot
let trustedCA
const secret = "sk-lumen-private-'$`quoted`-full-key"
const rotatedSecret = "sk-synthetic-rotated-key"
const catalogRows = [
	["lumen/1/101", "shared-model", "Sol fixture", "openai", "OpenAI fixture", "openai", ["messages", "responses"]],
	["lumen/2/201", "shared-model", "Luna fixture", "anthropic", "Anthropic fixture", "anthropic", ["messages", "responses"]],
	["lumen/3/301", "gemini-fable", "Fable fixture", "google", "Google fixture", "gemini", ["messages", "responses"]],
	["lumen/1/102", "openai-opus", "Opus fixture", "openai", "OpenAI fixture", "openai", ["messages", "responses"]],
	["lumen/2/202", "claude-sonnet", "Sonnet '$` fixture", "anthropic", "Anthropic fixture", "anthropic", ["messages", "responses"]],
	["lumen/3/302", "gemini-haiku", "Haiku fixture", "google", "Google fixture", "gemini", ["messages", "responses"]],
	["lumen/4/401", "subscription-message-only", "Message-only fixture", "claude-sub", "Claude subscription", "anthropic", ["messages"]],
	["lumen/5/501", "subscription-unsupported", "Unavailable fixture", "chatgpt", "ChatGPT subscription", "chatgpt", []],
].map(([id, api_model_name, display_name, provider, provider_name, provider_type, protocols]) => ({
	id, api_model_name, display_name, provider, provider_name, provider_type, protocols,
	usable: protocols.length > 0, disabled_reason: protocols.length ? null : "subscription_protocol_unsupported",
	capabilities: { context_limit: 128000, input_modalities: ["text"], reasoning_options: [] },
	input_price_per_million: "1.25", output_price_per_million: "4",
}))
const responsesModel = catalogRows[0].id
const commandEnv = {}
for (const name of ["PATH", "LANG", "LC_ALL", "TERM"]) {
	if (process.env[name] !== undefined) commandEnv[name] = process.env[name]
}


// A separate process serves HTTPS while the test thread is blocked in spawnSync.
// The installer uses a real certificate chain and HTTP request, not a fetch stub.
const catalogServer = String.raw`
import http.server, json, ssl, sys
fixture = json.load(sys.stdin)
requests = []
posts = []
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        requests.append(self.path)
        if self.path == '/requests':
            return self.reply(200, {'paths': requests})
        if self.path == '/posts':
            return self.reply(200, {'posts': posts})
        key = self.headers.get('Authorization', '').removeprefix('Bearer ')
        if key not in fixture['keys'] or self.path.startswith('/denied/'):
            # Reflected sensitive error content must never reach installer output.
            return self.reply(401, {'error': {'message': self.headers.get('Authorization')}})
        if self.path.startswith('/outage/'):
            return self.reply(503, {'error': {'message': 'storage offline'}})
        if self.path.startswith('/forbidden/'):
            return self.reply(403, {'error': {'message': 'missing models:read scope'}})
        if self.path.startswith('/old-server/'):
            return self.reply(404, {'detail': 'Not Found'})
        if self.path.startswith('/redirect/'):
            self.send_response(302)
            self.send_header('Location', '/redirect-target')
            self.end_headers()
            return
        models = fixture['models']
        if self.path.startswith('/empty/'):
            models = []
        elif self.path.startswith('/disabled/'):
            models = [{**row, 'protocols': [], 'usable': False, 'disabled_reason': 'pricing_unavailable'} for row in models]
        elif self.path.startswith('/duplicate/'):
            models = [*models, models[0]]
        elif self.path.startswith('/malformed/'):
            models = [{**models[0], 'capabilities': 'not an object'}]
        elif self.path.startswith('/capability-shape/'):
            models = [{**row, 'capabilities': {**row['capabilities'], 'input_modalities': 'image/text'}} for row in models]
        elif self.path.startswith('/control-label/'):
            models = [{**models[0], 'display_name': 'bad\x1blabel'}]
        self.reply(200, {'models': models})
    def do_POST(self):
        # Native Codex inference requests are captured, then stopped without a model call.
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        posts.append({'path': self.path, 'headers': {k.lower(): v for k, v in self.headers.items()},
                      'body': body.decode('utf-8', 'replace')})
        self.reply(400, {'error': {'message': 'synthetic stop', 'type': 'invalid_request_error'}})
    def reply(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(fixture['cert'], fixture['key'])
server.socket = context.wrap_socket(server.socket, server_side=True)
print(json.dumps({'port': server.server_port}), flush=True)
server.serve_forever()
`

test.before(async () => {
	tlsRoot = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "lumen-catalog-tls-")))
	const cert = path.join(tlsRoot, "cert.pem")
	const key = path.join(tlsRoot, "key.pem")
	const caCert = path.join(tlsRoot, "ca.pem")
	const caKey = path.join(tlsRoot, "ca-key.pem")
	const leafExtensions = path.join(tlsRoot, "leaf.ext")
	const openssl = (args) => {
		const result = spawnSync("openssl", args, { env: commandEnv, encoding: "utf8", timeout: 15000 })
		assert.equal(result.status, 0, result.stderr)
	}
	// A real CA-signed server leaf: native Codex (rustls) rejects a CA certificate used as the leaf.
	openssl(["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=Lumen installer test CA",
		"-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign",
		"-addext", "subjectKeyIdentifier=hash", "-keyout", caKey, "-out", caCert])
	openssl(["req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=127.0.0.1", "-keyout", key,
		"-out", path.join(tlsRoot, "leaf.csr")])
	fs.writeFileSync(leafExtensions, "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n" +
		"extendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n")
	openssl(["x509", "-req", "-in", path.join(tlsRoot, "leaf.csr"), "-CA", caCert, "-CAkey", caKey, "-set_serial", "1",
		"-days", "1", "-extfile", leafExtensions, "-out", cert])
	trustedCA = path.join(tlsRoot, "trusted-ca.pem")
	const system = process.platform === "darwin" ? "/private/etc/ssl/cert.pem" : "/etc/ssl/certs/ca-certificates.crt"
	fs.writeFileSync(trustedCA, Buffer.concat([fs.readFileSync(system), fs.readFileSync(caCert)]), { mode: 0o600 })
	tlsServer = spawn("python3", ["-c", catalogServer], { env: commandEnv, stdio: ["pipe", "pipe", "pipe"] })
	tlsServer.stdin.end(JSON.stringify({ cert, key, keys: [secret, rotatedSecret], models: catalogRows }))
	const port = await new Promise((resolve, reject) => {
		let output = ""
		let error = ""
		const timeout = setTimeout(() => reject(new Error("TLS catalog fixture did not become ready")), 10000)
		tlsServer.stderr.on("data", (data) => { error += data })
		tlsServer.once("error", reject)
		tlsServer.once("exit", () => reject(new Error("TLS catalog fixture exited: " + error)))
		tlsServer.stdout.on("data", (data) => {
			output += data
			if (output.includes("\n")) {
				clearTimeout(timeout)
				resolve(JSON.parse(output.trim()).port)
			}
		})
	})
	bases = [`https://127.0.0.1:${port}/responses/v1`, `https://127.0.0.1:${port}/anthropic`]
})

test.after(async () => {
	if (tlsServer && tlsServer.exitCode === null && tlsServer.signalCode === null) {
		const exited = new Promise((resolve) => tlsServer.once("exit", resolve))
		tlsServer.kill("SIGTERM")
		await exited
	}
	if (tlsRoot) fs.rmSync(tlsRoot, { recursive: true, force: true })
})

function catalogFixture(route) {
	return new Promise((resolve, reject) => {
		https.get(new URL(route, bases[0]), { ca: fs.readFileSync(trustedCA) }, (response) => {
			let content = ""
			response.on("data", (data) => { content += data })
			response.on("end", () => resolve(JSON.parse(content)))
		}).on("error", reject)
	})
}

async function catalogRequests() {
	return (await catalogFixture("/requests")).paths
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
consumed = 0
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
            position = output.find(action['prompt'].encode(), consumed)
            if position >= 0:
                consumed = position + len(action['prompt'].encode())
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

function fixture(t, config = "", cliConfig) {
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
	const cliConfigPath = path.join(codexHome, "lumen-cli.config.toml")
	if (cliConfig !== undefined) fs.writeFileSync(cliConfigPath, cliConfig, { mode: 0o640 })
	const env = { ...commandEnv, HOME: home, CODEX_HOME: codexHome, ZDOTDIR: zdotdir, XDG_CONFIG_HOME: xdg,
		CODEX_CA_CERTIFICATE: trustedCA }
	return { root, home, codexHome, zdotdir, xdg, profile, bashrc, zshrc, configPath, cliConfigPath,
		solConfigPath: path.join(codexHome, "lumen-sol.config.toml"),
		lunaConfigPath: path.join(codexHome, "lumen-luna.config.toml"),
		modelsPath: path.join(codexHome, "lumen-models.json"),
		keyPath: path.join(xdg, "lumen", "key.sh"), env }
}

function actions(optIn = "n", sol = "1", startup = "") {
	return [
		{ prompt: "Lumen API key: ", value: secret },
		{ prompt: "Codex Sol model number: ", value: sol },
		{ prompt: "Codex Luna model number: ", value: "2" },
		{ prompt: "Claude Fable model number: ", value: "3" },
		{ prompt: "Claude Opus model number: ", value: "4" },
		{ prompt: "Claude Sonnet model number: ", value: "5" },
		{ prompt: "Claude Haiku model number: ", value: "6" },
		{ prompt: "Claude startup role [sonnet]: ", value: startup },
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

function parseConfig(f, configPath = f.configPath) {
	const result = spawnSync("python3", ["-c", "import json,sys,tomllib; print(json.dumps(tomllib.load(open(sys.argv[1], 'rb'))))", configPath], { env: f.env, encoding: "utf8" })
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
	assert.equal(env.LUMEN_MODEL, undefined)
	assert.equal(env.LUMEN_CODEX_MODEL, undefined)
	assert.equal(env.ANTHROPIC_BASE_URL, bases[1])
	assert.equal(env.ANTHROPIC_MODEL, "sonnet")
	for (const [role, index] of [["FABLE", 2], ["OPUS", 3], ["SONNET", 4], ["HAIKU", 5]]) {
		assert.equal(env[`ANTHROPIC_DEFAULT_${role}_MODEL`], catalogRows[index].id)
	}
	assert.equal(env.CODEX_HOME, f.codexHome)
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
	const cliConfig = parseConfig(f, f.cliConfigPath)
	assert.equal(cliConfig.model, responsesModel)
	assert.equal(cliConfig.model_provider, "lumen-cli")
	assert.equal(parseConfig(f, f.solConfigPath).model, responsesModel)
	assert.equal(parseConfig(f, f.lunaConfigPath).model, catalogRows[1].id)
	assert.deepEqual(cliConfig.model_providers, { "lumen-cli": {
		name: "Lumen Responses", base_url: bases[0], env_key: "LUMEN_API_KEY", wire_api: "responses",
		requires_openai_auth: false, supports_websockets: false,
	} })
	for (const file of [f.profile, f.bashrc, f.zshrc, f.configPath, f.cliConfigPath,
		f.solConfigPath, f.lunaConfigPath, f.modelsPath]) assert.ok(!fs.readFileSync(file, "utf8").includes(secret))
	assert.equal(fs.statSync(f.profile).mode & 0o777, 0o640)
	assert.equal(fs.statSync(f.bashrc).mode & 0o777, 0o644)
	assert.equal(fs.statSync(f.zshrc).mode & 0o777, 0o644)
	assert.equal(fs.statSync(f.configPath).mode & 0o777, 0o600)
	assert.equal(fs.statSync(f.cliConfigPath).mode & 0o777, 0o600)
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
	const rotatedModel = catalogRows[1].id
	const rotation = actions("n", "2")
	rotation[0].value = rotatedSecret
	const rotated = install(f, { actions: rotation })
	assert.equal(rotated.status, 0, rotated.output)
	assert.ok(!rotated.output.includes(secret) && !rotated.output.includes(rotatedSecret))
	const reloaded = newShell(f, "bash")
	assert.equal(reloaded.LUMEN_API_KEY, rotatedSecret)
	assert.equal(reloaded.ANTHROPIC_AUTH_TOKEN, rotatedSecret)
	assert.equal(parseConfig(f, f.cliConfigPath).model, rotatedModel)
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

test("fresh-shell codex keeps management commands native and sends role routes without the desktop selector", async (t) => {
	const native = spawnSync("codex", ["--version"], { env: commandEnv, encoding: "utf8" })
	if (native.error?.code === "ENOENT") return t.skip("native Codex is not installed")
	const f = fixture(t, existingConfig)
	assert.equal(install(f).status, 0)
	// Test-only markers identify which native profile Codex actually loaded.
	for (const [file, name] of [[f.cliConfigPath, "lumen-cli"], [f.lunaConfigPath, "lumen-luna"]]) {
		fs.writeFileSync(file, `developer_instructions = "SELECTED ${name}"\n` + fs.readFileSync(file, "utf8"))
	}
	// codex exec reads piped stdin to EOF before the prompt is sent.
	const shell = (command) => spawnSync("bash", ["--noprofile", "-ic", command],
		{ cwd: f.root, env: f.env, encoding: "utf8", input: "", timeout: 60000 })
	for (const command of ["codex mcp list", "codex features list", "codex completion bash"]) {
		const result = shell(command)
		assert.equal(result.status, 0, `${command}: ${result.stderr}`)
	}
	const promptInput = (command) => {
		const result = shell(command)
		assert.equal(result.status, 0, `${command}: ${result.stderr}`)
		const items = JSON.parse(result.stdout)
		const text = (role) => items.filter((item) => item.role === role).map((item) => JSON.stringify(item.content)).join("\n")
		return { developer: text("developer"), user: text("user") }
	}
	assert.match(promptInput("codex debug prompt-input probe").developer, /SELECTED lumen-cli/)
	assert.match(promptInput("codex --profile lumen-luna debug prompt-input probe").developer, /SELECTED lumen-luna/)
	const boundary = promptInput("codex debug prompt-input -- --profile=lumen-luna")
	assert.match(boundary.developer, /SELECTED lumen-cli/)
	assert.match(boundary.user, /--profile=lumen-luna/)
	const before = (await catalogFixture("/posts")).posts.length
	for (const command of ["codex exec --skip-git-repo-check probe", "codex -p lumen-luna exec --skip-git-repo-check probe"]) {
		assert.notEqual(shell(command).status, 0, "the fixture stops inference after capturing the request")
	}
	const sent = (await catalogFixture("/posts")).posts.slice(before).filter((post) => post.path === "/responses/v1/responses")
	assert.deepEqual(sent.map((post) => JSON.parse(post.body).model), [responsesModel, catalogRows[1].id])
	for (const post of sent) {
		assert.equal(post.headers.authorization, `Bearer ${secret}`)
		assert.equal(post.headers["x-lumen-provider"], undefined, "desktop selector must not reach CLI role requests")
	}
	assert.equal(parseConfig(f).model_providers.lumen.http_headers["X-Lumen-Provider"], "provider-choice")
})

test("a Claude X-Lumen-Provider custom header refuses setup before the key prompt", (t) => {
	for (const headers of ["X-Lumen-Provider: openai", "X-Org-Route: prod\n x-lumen-provider : openai"]) {
		const f = fixture(t, existingConfig)
		f.env.ANTHROPIC_CUSTOM_HEADERS = headers
		const before = snapshot(f.root)
		const result = install(f, { actions: [] })
		assert.equal(result.status, 1, result.output)
		assert.equal(result.answered, 0)
		assert.match(result.output, /ANTHROPIC_CUSTOM_HEADERS sets X-Lumen-Provider/)
		assert.ok(!result.output.includes("openai"))
		assert.deepEqual(snapshot(f.root), before)
	}
	const f = fixture(t)
	f.env.ANTHROPIC_CUSTOM_HEADERS = "X-Org-Route: prod"
	assert.equal(install(f).status, 0)
	// Claude user settings env overrides the shell export, so it is checked too.
	const g = fixture(t, existingConfig)
	fs.mkdirSync(path.join(g.home, ".claude"), { mode: 0o700 })
	fs.writeFileSync(path.join(g.home, ".claude", "settings.json"),
		JSON.stringify({ env: { ANTHROPIC_CUSTOM_HEADERS: "X-Org-Route: prod\nX-Lumen-Provider: openai" } }))
	const before = snapshot(g.root)
	const refused = install(g, { actions: [] })
	assert.equal(refused.status, 1, refused.output)
	assert.match(refused.output, /ANTHROPIC_CUSTOM_HEADERS sets X-Lumen-Provider \(shell or Claude settings\.json env\)/)
	assert.deepEqual(snapshot(g.root), before)
})

test("opt-in changes only the top-level model", (t) => {
	const f = fixture(t, existingConfig)
	const result = install(f, { optIn: "yes" })
	assert.equal(result.status, 0, result.output)
	const config = parseConfig(f)
	assert.equal(config.model, catalogRows[0].api_model_name)
	assert.equal(config.model_provider, "openai")
	assert.equal(config.model_providers.lumen.http_headers["X-Lumen-Provider"], "provider-choice")
})

test("omitted URLs prompt through /dev/tty and default-model opt-in handles a file without a final newline", (t) => {
	const f = fixture(t, 'model_provider = "openai"')
	const result = install(f, { bases: [], actions: [
		{ prompt: "Codex HTTPS base URL: ", value: bases[0] },
		{ prompt: "Anthropic HTTPS base URL: ", value: bases[1] }, ...actions("y"),
	] })
	assert.equal(result.status, 0, result.output)
	assert.equal(result.answered, 11)
	assert.equal(parseConfig(f).model, catalogRows[0].api_model_name)
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


test("nonTTY failure does not consume stdin as a credential or modify profiles", (t) => {
	const f = fixture(t, existingConfig)
	const before = snapshot(f.home)
	for (const urls of [bases, []]) {
		const result = withoutTerminal(f, urls)
		assert.equal(result.status, 1)
		assert.ok(!result.output.includes(secret))
		assert.deepEqual(snapshot(f.home), before)
	}
})

test("invalid and incompatible selections cannot commit before a valid choice", (t) => {
	for (const invalid of ["0", "9", "bad model", "$(touch bad)", "-1", "7", "8"]) {
		const f = fixture(t, existingConfig)
		const before = snapshot(f.home)
		const chosen = actions().slice(0, 2)
		chosen[1].value = invalid
		chosen.push({ prompt: "Codex Sol model number: ", signal: "SIGTERM" })
		const result = install(f, { actions: chosen })
		assert.equal(result.status, 1, result.output)
		assert.equal(result.echoRestored, true)
		assert.ok(!result.output.includes(secret))
		assert.deepEqual(snapshot(f.home), before)
	}
	for (const options of [{ optIn: "maybe" }, { actions: actions("n", "1", "unknown") }]) {
		const f = fixture(t)
		const before = snapshot(f.home)
		assert.equal(install(f, options).status, 1)
		assert.deepEqual(snapshot(f.home), before)
	}
})

test("catalog auth, outage, unsafe metadata and untrusted TLS preserve the prior installation", (t) => {
	const messages = { forbidden: /models:read scope/, "old-server": /no Lumen CLI model catalog .*upgrade Lumen/,
		"capability-shape": /Invalid server model capability metadata/ }
	for (const failure of ["denied", "forbidden", "old-server", "outage", "empty", "disabled", "duplicate", "malformed",
		"capability-shape", "control-label", "untrusted"]) {
		const f = fixture(t, existingConfig)
		fs.mkdirSync(path.dirname(f.keyPath), { mode: 0o700 })
		fs.writeFileSync(f.keyPath, "export LUMEN_API_KEY=prior-private-key\n", { mode: 0o600 })
		if (failure === "untrusted") {
			f.env.CODEX_CA_CERTIFICATE = process.platform === "darwin" ? "/private/etc/ssl/cert.pem" : "/etc/ssl/certs/ca-certificates.crt"
		}
		const before = snapshot(f.root)
		const urls = failure === "untrusted" ? bases : [new URL(`/${failure}/v1`, bases[0]).href, bases[1]]
		const result = install(f, { bases: urls, actions: actions().slice(0, 1), trace: true })
		assert.equal(result.status, 1, result.output)
		assert.equal(result.keyEcho, false)
		assert.equal(result.echoRestored, true)
		assert.ok(!result.output.includes(secret) && !result.output.includes("prior-private-key"))
		assert.deepEqual(snapshot(f.root), before, failure)
		if (messages[failure]) assert.match(result.output, messages[failure], failure)
	}
})

test("catalog redirects cannot send the key to another route or commit local state", async (t) => {
	const f = fixture(t, existingConfig)
	const before = snapshot(f.root)
	const result = install(f, { bases: [new URL("/redirect/v1", bases[0]).href, bases[1]], actions: actions().slice(0, 1) })
	assert.equal(result.status, 1, result.output)
	assert.ok(!result.output.includes(secret))
	assert.deepEqual(snapshot(f.root), before)
	assert.equal((await catalogRequests()).some((route) => route === "/redirect-target"), false)
})

test("a corrected compatible choice and a different startup role preserve independent family targets", (t) => {
	const f = fixture(t)
	const selected = actions("n", "7", "fable")
	selected.splice(2, 0, { prompt: "Codex Sol model number: ", value: "3" })
	const result = install(f, { actions: selected })
	assert.equal(result.status, 0, result.output)
	assert.equal(parseConfig(f, f.cliConfigPath).model, catalogRows[2].id)
	assert.equal(parseConfig(f, f.lunaConfigPath).model, catalogRows[1].id)
	const env = newShell(f, "bash")
	assert.equal(env.ANTHROPIC_MODEL, "fable")
	for (const [role, index] of [["FABLE", 2], ["OPUS", 3], ["SONNET", 4], ["HAIKU", 5]]) {
		assert.equal(env[`ANTHROPIC_DEFAULT_${role}_MODEL`], catalogRows[index].id)
	}
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
	const bundle = path.join(f.home, "trusted.pem")
	fs.copyFileSync(trustedCA, bundle)
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
	fs.copyFileSync(trustedCA, override)
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

test("native lumen-cli profile preserves unrelated settings, leaves earlier provider tables unselected and updates managed defaults on rerun", (t) => {
	for (const cliText of [
		existingConfig,
		'model_providers = { lumen = { name = "old", http_headers = { "X-Lumen-Provider" = "chosen" } }, other = { name = "Keep" } }\n',
		'[model_providers]\nlumen = { name = "old", http_headers = { "X-Lumen-Provider" = "chosen" } }\nother = { name = "Keep" }\n',
		'model_providers.lumen.name = "old"\n[model_providers.lumen.http_headers]\n"X-Lumen-Provider" = "chosen"\n[model_providers.other]\nname = "Keep"',
	]) {
		const f = fixture(t, existingConfig, cliText)
		const original = parseConfig(f, f.cliConfigPath)
		const expected = {
			...original, model_provider: "lumen-cli", model: responsesModel, model_catalog_json: f.modelsPath,
			model_providers: { ...original.model_providers, "lumen-cli": {
				name: "Lumen Responses", base_url: bases[0], env_key: "LUMEN_API_KEY", wire_api: "responses",
				requires_openai_auth: false, supports_websockets: false,
			} },
		}
		assert.equal(install(f).status, 0)
		assert.deepEqual(parseConfig(f, f.cliConfigPath), expected)
		assert.equal(fs.statSync(f.cliConfigPath).mode & 0o777, 0o600)
		const rootConfig = parseConfig(f)
		const backups = fs.readdirSync(f.codexHome).filter((name) => name.startsWith(".lumen-cli.config.toml.lumen-backup-"))
		assert.equal(backups.length, 1)
		assert.equal(fs.readFileSync(path.join(f.codexHome, backups[0]), "utf8"), cliText)
		assert.equal(fs.statSync(path.join(f.codexHome, backups[0])).mode & 0o777, 0o600)
		const first = snapshot(f.home)
		assert.equal(install(f).status, 0)
		assert.deepEqual(snapshot(f.home), first, "identical native profile rerun must not create backups or change content")
		const rotatedBases = [new URL("/rotated/responses/v1", bases[0]).href, bases[1]]
		const rotatedModel = catalogRows[1].id
		// Simulate user edits to managed fields without depending on TOML output
		// formatting; rerun must repair provider/model as well as the endpoint.
		fs.writeFileSync(f.cliConfigPath, cliText)
		assert.equal(install(f, { bases: rotatedBases, actions: actions("n", "2") }).status, 0)
		expected.model = rotatedModel
		expected.model_providers["lumen-cli"].base_url = rotatedBases[0]
		assert.deepEqual(parseConfig(f, f.cliConfigPath), expected)
		rootConfig.model_providers.lumen.base_url = rotatedBases[0]
		assert.deepEqual(parseConfig(f), rootConfig, "rerun must preserve every desktop setting outside the managed provider")
		for (const [name, value] of Object.entries(snapshot(f.home))) {
			if (path.join(f.home, name) === f.keyPath || value.content === null) continue
			assert.ok(!value.content.includes(secret), "native profile and its backups must never contain the key")
		}
	}
})


test("unsafe native profile paths and malformed TOML fail before prompting or writing any target", (t) => {
	for (const hazard of ["symlink", "hardlink", "directory", "writable", "toml"]) {
		const f = fixture(t, existingConfig)
		const outside = path.join(f.root, "outside")
		fs.writeFileSync(outside, existingConfig, { mode: 0o600 })
		if (hazard === "symlink") fs.symlinkSync(outside, f.cliConfigPath)
		else if (hazard === "hardlink") fs.linkSync(outside, f.cliConfigPath)
		else if (hazard === "directory") fs.mkdirSync(f.cliConfigPath, { mode: 0o700 })
		else if (hazard === "writable") fs.writeFileSync(f.cliConfigPath, existingConfig, { mode: 0o600 })
		else fs.writeFileSync(f.cliConfigPath, "model = [broken\n", { mode: 0o600 })
		if (hazard === "writable") fs.chmodSync(f.cliConfigPath, 0o622)
		const before = snapshot(f.root)
		const result = install(f, { actions: [] })
		assert.equal(result.status, 1, result.output)
		assert.equal(result.answered, 0)
		assert.ok(!result.output.includes(secret))
		assert.deepEqual(snapshot(f.root), before, hazard)
	}
})
