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
