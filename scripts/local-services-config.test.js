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

function render(directory, envFile, environment) {
	const result = spawnSync("docker", ["compose", "--env-file", envFile, "-f", "docker-compose.dev.yml", "--profile", "notion-worker", "config", "--format", "json"], {
		cwd: directory, env: environment, encoding: "utf8", timeout: 20000, maxBuffer: 4 * 1024 * 1024,
	});
	assert.ok(!result.error && result.status === 0, "actual Compose private-file render failed (output withheld)");
	const inputs = spawnSync("docker", ["compose", "--env-file", envFile, "-f", "docker-compose.dev.yml", "config", "--environment"], {
		cwd: directory, env: environment, encoding: "utf8", timeout: 20000, maxBuffer: 4 * 1024 * 1024,
	});
	assert.ok(!inputs.error && inputs.status === 0, "actual Compose interpolation inspection failed (output withheld)");
	const values = Object.fromEntries(inputs.stdout.trim().split("\n").map((line) => {
		const separator = line.indexOf("=");
		return [line.slice(0, separator), line.slice(separator + 1)];
	}));
	return { config: JSON.parse(result.stdout), values };
}

function assertDestinations({ config, values }, expected) {
	for (const owner of owners) {
		assert.ok(values[`${owner.toUpperCase()}_DATABASE_URL`] === expected[`${owner.toUpperCase()}_DATABASE_URL`], `${owner} credential changed in the prepared env file (values withheld)`);
		for (const service of consumers[owner]) {
			// Rendered config escapes '$'; the interpolation values above remain raw.
			assert.ok(config.services[service].environment.DATABASE_URL === expected[`${owner.toUpperCase()}_DATABASE_URL`].split('$').join('$$'), `${service} lost its selected database (values withheld)`);
		}
	}
}

for (const source of ["dotenv", "shell"]) {
	test(`services:config preserves ${source} database destinations in a credential-safe private env file`, (t) => {
		const temp = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-config-db-"));
		t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
		const directory = path.join(temp, "afterglow");
		fs.mkdirSync(directory);
		fs.copyFileSync(path.join(root, "docker-compose.dev.yml"), path.join(directory, "docker-compose.dev.yml"));
		for (const owner of owners.filter((owner) => owner !== "afterglow")) fs.mkdirSync(path.join(temp, owner));
		fs.writeFileSync(path.join(directory, "afterglow.conf"), '[openstack]\nauth_url = "https://identity.invalid/v3"\nusername = "synthetic"\npassword = "synthetic"\nservice_project_id = "synthetic-service-project"\n');
		writeEnvironment(path.join(directory, ".env"), { ...databaseUrls("dotenv"), WAYGATE_PUBLIC_BASE_URL: "https://callback.invalid" });
		const environment = cleanEnvironment();
		if (source === "shell") Object.assign(environment, databaseUrls("shell"));
		const expected = databaseUrls(source);
		const result = spawnSync(process.execPath, [runner, "config"], { cwd: directory, env: environment, encoding: "utf8", timeout: 30000, maxBuffer: 1024 * 1024 });
		assert.ok(!result.error && result.status === 0, "services:config rejected operator-selected databases (output withheld)");
		const output = result.stdout + result.stderr;
		assert.ok(!output.includes("literal$NOT_EXPANDED") && !output.includes(`${source}.invalid`), "database credentials/destinations must not be logged");
		const privateFile = path.join(directory, ".local-services", "compose.env");
		if (process.platform !== "win32") assert.equal(fs.statSync(privateFile).mode & 0o777, 0o600);
		// Removing the original input proves this entry path uses the prepared values.
		writeEnvironment(path.join(directory, ".env"), { WAYGATE_PUBLIC_BASE_URL: "https://callback.invalid" });
		assertDestinations(render(directory, privateFile, cleanEnvironment()), expected);
		const secretsBefore = fs.readFileSync(path.join(directory, ".local-services", "secrets.json"));
		const repeat = spawnSync(process.execPath, [runner, "config"], { cwd: directory, env: { ...cleanEnvironment(), ...databaseUrls("next") }, encoding: "utf8", timeout: 30000 });
		assert.ok(!repeat.error && repeat.status === 0, "database reselection failed (output withheld)");
		assertDestinations(render(directory, privateFile, cleanEnvironment()), databaseUrls("next"));
		assert.ok(fs.readFileSync(path.join(directory, ".local-services", "secrets.json")).equals(secretsBefore), "database reselection must not rotate existing keys");
	});
}

const crypto = require("node:crypto");
const digest = (value) => crypto.createHash("sha256").update(value).digest("hex");

function lumenProject(t, { scopedKey, lumenContext } = {}) {
	const temp = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-config-lumen-"));
	t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
	const directory = path.join(temp, "afterglow");
	fs.mkdirSync(directory);
	fs.copyFileSync(path.join(root, "docker-compose.dev.yml"), path.join(directory, "docker-compose.dev.yml"));
	for (const owner of owners.filter((owner) => owner !== "afterglow")) fs.mkdirSync(path.join(temp, owner));
	fs.writeFileSync(path.join(directory, "afterglow.conf"), '[openstack]\nauth_url = "https://identity.invalid/v3"\nusername = "synthetic"\npassword = "synthetic"\nservice_project_id = "synthetic-service-project"\n');
	const dotenv = { WAYGATE_PUBLIC_BASE_URL: "https://callback.invalid" };
	if (lumenContext) {
		fs.mkdirSync(path.join(lumenContext, "docker"), { recursive: true });
		fs.writeFileSync(path.join(lumenContext, "docker", "Dockerfile"), "FROM scratch\n");
		dotenv.LUMEN_BUILD_CONTEXT = lumenContext;
	}
	writeEnvironment(path.join(directory, ".env"), dotenv);
	if (scopedKey) {
		fs.mkdirSync(path.join(directory, ".local-services"), { recursive: true, mode: 0o700 });
		fs.writeFileSync(path.join(directory, ".local-services", "lumen.env"), `LUMEN_ENCRYPTION_KEY=${JSON.stringify(scopedKey)}\n`, { mode: 0o600 });
	}
	return directory;
}

function runConfig(directory) {
	const result = spawnSync(process.execPath, [runner, "config"], { cwd: directory, env: cleanEnvironment(), encoding: "utf8", timeout: 30000, maxBuffer: 1024 * 1024 });
	assert.ok(!result.error && result.status === 0, "services:config rejected the Lumen compatibility inputs (output withheld)");
	return result.stdout + result.stderr;
}

function lumenKeyHashes(directory) {
	const rendered = spawnSync("docker", ["compose", "--env-file", path.join(directory, ".local-services", "compose.env"), "-f", "docker-compose.dev.yml", "--profile", "notion-worker", "config", "--format", "json"], { cwd: directory, env: cleanEnvironment(), encoding: "utf8", timeout: 20000, maxBuffer: 4 * 1024 * 1024 });
	assert.ok(!rendered.error && rendered.status === 0, "actual Compose render failed (output withheld)");
	const services = JSON.parse(rendered.stdout).services;
	return Object.fromEntries(Object.entries(services).map(([name, service]) => [name, service.environment?.LUMEN_ENCRYPTION_KEY ? digest(service.environment.LUMEN_ENCRYPTION_KEY) : null]));
}

test("an existing scoped Lumen key is preserved and reaches only the Lumen consumers", (t) => {
	const scopedKey = "synthetic-production-lumen-key-that-must-survive";
	const directory = lumenProject(t, { scopedKey });
	const output = runConfig(directory);
	assert.ok(!output.includes(scopedKey), "the scoped Lumen key must never be logged");
	const hashes = lumenKeyHashes(directory);
	for (const service of consumers.lumen) assert.ok(hashes[service] === digest(scopedKey), `${service} did not receive the preserved scoped key (values withheld)`);
	const leaked = Object.entries(hashes).filter(([name, value]) => value === digest(scopedKey) && !consumers.lumen.includes(name)).map(([name]) => name);
	assert.deepEqual(leaked, [], "the Lumen key leaked into non-Lumen services");
	assert.ok(fs.readFileSync(path.join(directory, ".local-services", "lumen.env"), "utf8").includes(JSON.stringify(scopedKey)), "an existing scoped key file must not be rewritten");
	runConfig(directory);
	assert.ok(lumenKeyHashes(directory)["lumen-api"] === digest(scopedKey), "a repeated configuration run rotated the preserved key");
});

test("a missing scoped Lumen key is generated once with owner-only access and then kept", (t) => {
	const directory = lumenProject(t);
	runConfig(directory);
	const file = path.join(directory, ".local-services", "lumen.env");
	if (process.platform !== "win32") assert.equal(fs.statSync(file).mode & 0o777, 0o600);
	const first = fs.readFileSync(file, "utf8");
	assert.match(first, /^LUMEN_ENCRYPTION_KEY="[a-f0-9]{64}"\n$/);
	runConfig(directory);
	assert.equal(fs.readFileSync(file, "utf8"), first, "a generated scoped key must not rotate on the next run");
});

test("a pinned Lumen compatibility source is the build context for every Lumen image", (t) => {
	const pinned = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-lumen-source-")), "lumen-pinned");
	t.after(() => fs.rmSync(path.dirname(pinned), { recursive: true, force: true }));
	const directory = lumenProject(t, { lumenContext: pinned });
	runConfig(directory);
	const rendered = spawnSync("docker", ["compose", "--env-file", path.join(directory, ".local-services", "compose.env"), "-f", "docker-compose.dev.yml", "config", "--format", "json"], { cwd: directory, env: cleanEnvironment(), encoding: "utf8", timeout: 20000, maxBuffer: 4 * 1024 * 1024 });
	assert.ok(!rendered.error && rendered.status === 0, "actual Compose render failed (output withheld)");
	const services = JSON.parse(rendered.stdout).services;
	for (const service of consumers.lumen) assert.equal(fs.realpathSync(services[service].build.context), fs.realpathSync(pinned), `${service} ignored the pinned compatibility source`);
	for (const service of ["drover-api", "waygate-api", "palimpsest-api"]) assert.ok(!String(services[service].build.context).includes("lumen-pinned"), `${service} must not follow the Lumen source selection`);
});

test("an unavailable pinned Lumen source stops before anything starts", (t) => {
	const directory = lumenProject(t);
	fs.appendFileSync(path.join(directory, ".env"), `LUMEN_BUILD_CONTEXT='${path.join(os.tmpdir(), "afterglow-missing-lumen-source")}'\n`);
	const result = spawnSync(process.execPath, [runner, "up"], { cwd: directory, env: cleanEnvironment(), encoding: "utf8", timeout: 30000, maxBuffer: 1024 * 1024 });
	assert.ok(result.status !== 0, "a missing pinned Lumen source must be rejected");
	assert.match(result.stdout + result.stderr, /current sibling source is unavailable: Lumen/);
});
