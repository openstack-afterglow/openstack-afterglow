const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const runner = path.join(root, "scripts", "local-services.mjs");
const owners = ["afterglow", "drover", "lumen", "waygate", "palimpsest"];
const consumers = {
	afterglow: ["backend", "notion-worker"],
	drover: ["drover-api", "drover-worker", "drover-migrate"],
	lumen: ["lumen-api", "lumen-worker", "lumen-migrate"],
	waygate: ["waygate-api", "waygate-worker", "waygate-migrate"],
	palimpsest: ["palimpsest-api", "palimpsest-worker", "palimpsest-bootstrap"],
};
// Synthetic 64-hex values; never real keys. Assertions use assert.ok so failures never print them.
const SECRETS = {
	AFTERGLOW_LOCAL_SECRET_KEY: "a1".repeat(32),
	AFTERGLOW_LOCAL_ENCRYPTION_KEY: "b2".repeat(32),
	AFTERGLOW_LOCAL_SERVICE_TOKEN: "c3".repeat(32),
};

function cleanEnvironment() {
	return Object.fromEntries(["PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SystemRoot", "WINDIR", "DOCKER_CONFIG"]
		.filter((key) => process.env[key] !== undefined)
		.map((key) => [key, process.env[key]]));
}

function databaseUrls(source) {
	return Object.fromEntries(owners.map((owner) => [
		`${owner.toUpperCase()}_DATABASE_URL`,
		`mysql+${owner === "palimpsest" ? "asyncmy" : "aiomysql"}://${owner}:literal$NOT_EXPANDED%22password@${source}.invalid:3306/${owner}?charset=utf8mb4`,
	]));
}

function writeEnvironment(file, values) {
	fs.writeFileSync(file, Object.entries(values).map(([key, value]) => `${key}='${value}'`).join("\n") + "\n", { mode: 0o600 });
}

// A project with the real compose file, a root afterglow.conf and a root .env, the same inputs an operator uses.
function project(t, { conf = "", dotenv = {}, password = "synthetic", mode = 0o644 } = {}) {
	const temp = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-config-local-"));
	t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
	const directory = path.join(temp, "afterglow");
	fs.mkdirSync(directory);
	fs.copyFileSync(path.join(root, "docker-compose.dev.yml"), path.join(directory, "docker-compose.dev.yml"));
	for (const owner of owners.filter((owner) => owner !== "afterglow")) fs.mkdirSync(path.join(temp, owner));
	const passwordLine = password === null ? "" : `password = "${password}"\n`;
	const configFile = path.join(directory, "afterglow.conf");
	fs.writeFileSync(configFile, `[openstack]\nauth_url = "https://identity.invalid/v3"\nusername = "synthetic"\n${passwordLine}service_project_id = "synthetic-service-project"\n${conf}`);
	fs.chmodSync(configFile, mode);
	writeEnvironment(path.join(directory, ".env"), { ...databaseUrls("dotenv"), WAYGATE_PUBLIC_BASE_URL: "https://callback.invalid", ...SECRETS, ...dotenv });
	return directory;
}

function runLocal(directory, args, environment = cleanEnvironment()) {
	return spawnSync(process.execPath, [runner, ...args], { cwd: directory, env: environment, encoding: "utf8", timeout: 60000, maxBuffer: 4 * 1024 * 1024 });
}

// Compose reads .env itself; the shell environment wins over it, as in a real invocation.
function renderConfig(directory, environment = cleanEnvironment()) {
	const result = spawnSync("docker", ["compose", "--env-file", ".env", "-f", "docker-compose.dev.yml", "--profile", "notion-worker", "config", "--format", "json"], {
		cwd: directory, env: environment, encoding: "utf8", timeout: 30000, maxBuffer: 8 * 1024 * 1024,
	});
	assert.ok(!result.error && result.status === 0, "actual Compose render failed (output withheld)");
	return JSON.parse(result.stdout).services;
}

test("services:config reads the root .env and afterglow.conf and creates no private directory", (t) => {
	const directory = project(t, { conf: '\n[local]\ndrover_callback_base_url = "https://from-conf.invalid"\n' });
	const result = runLocal(directory, ["config"]);
	assert.ok(!result.error && result.status === 0, "services:config rejected valid root inputs (output withheld)");
	assert.ok(!fs.existsSync(path.join(directory, ".local-services")), "the removed private directory must not be recreated");
	assert.match(result.stdout, /DROVER_CALLBACK_BASE_URL: afterglow\.conf \[local\]/);
	assert.ok(!(result.stdout + result.stderr).includes("from-conf.invalid"), "configured values must not be printed");
});

test("shell env beats .env, which beats afterglow.conf [local]; compose renders the winning value", (t) => {
	const directory = project(t, {
		conf: '\n[local]\ndrover_callback_base_url = "https://from-conf.invalid"\nwaygate_public_base_url = "https://from-conf-waygate.invalid"\n',
		dotenv: { DROVER_CALLBACK_BASE_URL: "https://from-dotenv.invalid", WAYGATE_PUBLIC_BASE_URL: "https://from-dotenv-waygate.invalid" },
	});
	const environment = { ...cleanEnvironment(), WAYGATE_PUBLIC_BASE_URL: "https://from-shell.invalid" };
	const result = runLocal(directory, ["config"], environment);
	assert.ok(!result.error && result.status === 0, "services:config rejected overridden [local] inputs (output withheld)");
	assert.match(result.stdout, /DROVER_CALLBACK_BASE_URL: \.env/);
	assert.match(result.stdout, /WAYGATE_PUBLIC_BASE_URL: shell environment/);
	const services = renderConfig(directory, environment);
	assert.ok(services["drover-api"].environment.DROVER_CALLBACK_BASE_URL === "https://from-dotenv.invalid", ".env must beat afterglow.conf");
	assert.ok(services["waygate-api"].environment.WAYGATE_CALLBACK_BASE_URL === "https://from-shell.invalid", "the shell environment must beat .env and afterglow.conf");
});

test("an OpenStack password supplied only in .env is accepted and never printed", (t) => {
	const password = "synthetic-env-password-7c1e";
	const directory = project(t, { password: null, dotenv: { AFTERGLOW_LOCAL_OS_PASSWORD: password } });
	const result = runLocal(directory, ["config"]);
	assert.ok(!result.error && result.status === 0, "services:config rejected a password supplied through .env (output withheld)");
	assert.ok(!(result.stdout + result.stderr).includes(password), "the OpenStack password must never be printed");
	assert.match(result.stdout, /AFTERGLOW_LOCAL_OS_PASSWORD: \.env/);
});

test("a missing OpenStack password is refused and the message names the sources without printing values", (t) => {
	const directory = project(t, { password: null });
	const result = runLocal(directory, ["config"]);
	assert.ok(result.status !== 0, "a missing password must be rejected");
	assert.match(result.stdout + result.stderr, /auth_url, username and password/);
});

test("a missing local secret is refused by name and no secret value is printed", (t) => {
	const directory = project(t, { dotenv: { AFTERGLOW_LOCAL_SERVICE_TOKEN: "" } });
	const result = runLocal(directory, ["config"]);
	assert.ok(result.status !== 0, "an empty local secret must be rejected");
	const output = result.stdout + result.stderr;
	assert.match(output, /AFTERGLOW_LOCAL_SERVICE_TOKEN must be 64 lowercase hex characters/);
	assert.ok(!output.includes(SECRETS.AFTERGLOW_LOCAL_SECRET_KEY) && !output.includes(SECRETS.AFTERGLOW_LOCAL_ENCRYPTION_KEY), "secret values must not be printed");
});

test("the Lumen encryption key comes from .env and reaches only the Lumen services", (t) => {
	const directory = project(t);
	const services = renderConfig(directory);
	for (const service of consumers.lumen) {
		assert.ok(services[service].environment.LUMEN_ENCRYPTION_KEY === SECRETS.AFTERGLOW_LOCAL_ENCRYPTION_KEY, `${service} did not receive the .env encryption key (values withheld)`);
	}
	const leaked = Object.keys(services).filter((name) => !consumers.lumen.includes(name) && services[name].environment?.LUMEN_ENCRYPTION_KEY !== undefined);
	assert.deepEqual(leaked, [], "the Lumen encryption key must not reach non-Lumen services");
});

test("afterglow.conf that the non-root containers cannot read is refused with the fix", { skip: process.platform === "win32" }, (t) => {
	const directory = project(t, { mode: 0o600 });
	const result = runLocal(directory, ["config"]);
	assert.ok(result.status !== 0, "an unreadable afterglow.conf must be rejected");
	assert.match(result.stdout + result.stderr, /chmod 0644 afterglow\.conf/);
});

test("secret-like keys are refused in afterglow.conf [local] and their values are never printed", (t) => {
	const secret = "synthetic-secret-value-9f3c";
	const directory = project(t, { conf: `\n[local]\ngrafana_password = "${secret}"\n` });
	const result = runLocal(directory, ["config"]);
	assert.ok(result.status !== 0, "a secret-like [local] key must be rejected");
	const output = result.stdout + result.stderr;
	assert.match(output, /unsupported keys/);
	assert.ok(!output.includes(secret), "the rejected secret value must not be printed");
});

test("a pinned Lumen compatibility source is the build context for every Lumen service", (t) => {
	const pinned = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-lumen-source-"));
	t.after(() => fs.rmSync(pinned, { recursive: true, force: true }));
	const directory = project(t, { dotenv: { LUMEN_BUILD_CONTEXT: pinned } });
	const services = renderConfig(directory);
	for (const service of consumers.lumen) {
		assert.ok(fs.realpathSync(services[service].build.context) === fs.realpathSync(pinned), `${service} ignored the pinned compatibility source`);
	}
	for (const service of ["drover-api", "waygate-api", "palimpsest-api"]) {
		assert.ok(!String(services[service].build.context).includes(path.basename(pinned)), `${service} must not follow the Lumen source selection`);
	}
});

test("an unavailable pinned Lumen source stops up before anything starts", (t) => {
	const missing = path.join(os.tmpdir(), "afterglow-missing-lumen-source");
	const directory = project(t, { dotenv: { LUMEN_BUILD_CONTEXT: missing } });
	const result = runLocal(directory, ["up"]);
	assert.ok(result.status !== 0, "a missing pinned Lumen source must be rejected");
	assert.match(result.stdout + result.stderr, /current sibling source is unavailable: Lumen/);
});

for (const source of ["dotenv", "shell"]) {
	test(`${source} database destinations reach their consumers through compose without a private copy`, (t) => {
		const directory = project(t);
		const environment = source === "shell" ? { ...cleanEnvironment(), ...databaseUrls("shell") } : cleanEnvironment();
		const expected = databaseUrls(source);
		const result = runLocal(directory, ["config"], environment);
		assert.ok(!result.error && result.status === 0, "services:config rejected operator-selected databases (output withheld)");
		const output = result.stdout + result.stderr;
		assert.ok(!output.includes("literal$NOT_EXPANDED") && !output.includes(`${source}.invalid`), "database credentials/destinations must not be logged");
		const services = renderConfig(directory, environment);
		for (const owner of owners) {
			for (const service of consumers[owner]) {
				// Rendered config escapes '$'; the expected value is escaped the same way.
				assert.ok(services[service].environment.DATABASE_URL === expected[`${owner.toUpperCase()}_DATABASE_URL`].split("$").join("$$"), `${service} lost its selected database (values withheld)`);
			}
		}
	});
}

test("an explicit LUMEN_ENCRYPTION_KEY in .env reaches the Lumen services as a distinct key", (t) => {
	const distinct = "d4".repeat(32);
	const directory = project(t, { dotenv: { LUMEN_ENCRYPTION_KEY: distinct } });
	const services = renderConfig(directory);
	for (const service of consumers.lumen) {
		assert.ok(services[service].environment.LUMEN_ENCRYPTION_KEY === distinct, `${service} did not receive the distinct .env Lumen key (values withheld)`);
		assert.ok(services[service].environment.LUMEN_ENCRYPTION_KEY !== SECRETS.AFTERGLOW_LOCAL_ENCRYPTION_KEY, `${service} must not fall back to the Afterglow key when LUMEN_ENCRYPTION_KEY is set`);
	}
});

// Known gap: every service loads .env through env_file, so .env names (including this key) also appear in
// non-Lumen containers. Isolation needs a compose decision (remove env_file, or keep dev-only exposure).
test("the Lumen encryption key does not reach non-Lumen containers", { todo: "env_file: .env exposes every .env name to every service; open decision" }, (t) => {
	const distinct = "d4".repeat(32);
	const directory = project(t, { dotenv: { LUMEN_ENCRYPTION_KEY: distinct } });
	const services = renderConfig(directory);
	const leaked = Object.keys(services).filter((name) => !consumers.lumen.includes(name) && services[name].environment?.LUMEN_ENCRYPTION_KEY !== undefined);
	assert.deepEqual(leaked, [], "no Lumen encryption key may reach non-Lumen services");
});

test("ceph and geoip host paths set in .env pass the mount allowlist and reach the backend", (t) => {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-config-mounts-"));
	t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
	const files = { ceph: path.join(dir, "ceph.conf"), keyring: path.join(dir, "ceph.client.afterglow-rbd.keyring"), geoip: path.join(dir, "country.mmdb") };
	for (const file of Object.values(files)) fs.writeFileSync(file, "synthetic\n");
	const directory = project(t, { dotenv: { AFTERGLOW_LOCAL_CEPH_CONF: files.ceph, AFTERGLOW_LOCAL_CEPH_KEYRING: files.keyring, TRAFFIC_ANALYTICS_GEOIP_MMDB_FILE: files.geoip } });
	const result = runLocal(directory, ["config"]);
	assert.ok(!result.error && result.status === 0, "services:config rejected host mounts configured in .env (output withheld)");
	const sources = renderConfig(directory).backend.volumes.map((mount) => mount.source).filter(Boolean);
	for (const file of Object.values(files)) {
		assert.ok(sources.some((source) => fs.existsSync(source) && fs.realpathSync(source) === fs.realpathSync(file)), "a .env host path must reach the backend mount");
	}
});
