const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const manifestPath = path.resolve(__dirname, "..", "docker-compose.dev.yml");
const databaseVariables = [
	"DATABASE_URL",
	"AFTERGLOW_DATABASE_URL",
	"WAYGATE_DATABASE_URL",
	"DROVER_DATABASE_URL",
	"LUMEN_DATABASE_URL",
	"PALIMPSEST_DATABASE_URL",
];
const expectedDatabases = {
	backend: "mysql+aiomysql://afterglow:dev@afterglow-mariadb:3306/afterglow",
	"notion-worker": "mysql+aiomysql://afterglow:dev@afterglow-mariadb:3306/afterglow",
};
for (const service of ["waygate", "drover", "lumen", "palimpsest"]) {
	const driver = service === "palimpsest" ? "asyncmy" : "aiomysql";
	const oneOff = service === "palimpsest" ? "bootstrap" : "migrate";
	for (const role of ["api", "worker", oneOff]) {
		expectedDatabases[`${service}-${role}`] = `mysql+${driver}://${service}:dev@service-mariadb:3306/${service}`;
	}
}

function remoteEnvironment(source) {
	return {
		...Object.fromEntries(databaseVariables.map((name) => [
			name,
			`mysql+aiomysql://${source}_user:dummy_password@${source}.invalid:3306/remote_${name.toLowerCase()}`,
		])),
		// A non-DB interpolation witness proves which input Compose actually used.
		WAYGATE_PUBLIC_BASE_URL: `https://${source}.invalid/callback`,
	};
}

function writeEnvironment(filePath, environment) {
	fs.writeFileSync(filePath, Object.entries(environment).map(([key, value]) => `${key}=${value}\n`).join(""), { mode: 0o600 });
}

function dockerEnvironment() {
	// Keep CLI discovery/configuration, but never inherit app secrets or COMPOSE_* inputs.
	const environment = {};
	for (const key of ["PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SystemRoot", "WINDIR", "DOCKER_CONFIG"]) {
		if (process.env[key] !== undefined) environment[key] = process.env[key];
	}
	return environment;
}

function composeConfig(projectDir, privateEnvFile, environment) {
	const args = ["compose", "-f", "docker-compose.dev.yml", "--profile", "notion-worker"];
	if (privateEnvFile) args.push("--env-file", privateEnvFile);
	args.push("config", "--format", "json");
	const result = spawnSync("docker", args, {
		cwd: projectDir,
		env: environment,
		encoding: "utf8",
		stdio: ["ignore", "pipe", "pipe"],
		timeout: 15000,
		killSignal: "SIGKILL",
		maxBuffer: 4 * 1024 * 1024,
	});
	// Never attach stdout/stderr: rendered config can contain credential values.
	assert.ok(!result.error, `docker compose config could not run (${result.error?.code ?? "unknown"}); Docker Compose is required`);
	assert.ok(result.status === 0, `docker compose config failed (exit ${result.status}, signal ${result.signal ?? "none"})`);
	try {
		return JSON.parse(result.stdout);
	} catch {
		assert.fail("docker compose config did not return valid JSON (output withheld)");
	}
}

test("development Compose isolates every application database from env-file and shell overrides", async (t) => {
	const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-datastore-"));
	try {
		const projectDir = path.join(tempDir, "afterglow");
		fs.mkdirSync(projectDir);
		// Copy unchanged, not symlinked: .env, mounts and sibling build contexts must
		// resolve relative to this temporary project, never the real checkout.
		fs.copyFileSync(manifestPath, path.join(projectDir, "docker-compose.dev.yml"));
		for (const sibling of ["waygate", "drover", "lumen", "palimpsest"]) {
			fs.mkdirSync(path.join(tempDir, sibling));
		}
		writeEnvironment(path.join(projectDir, ".env"), remoteEnvironment("dotenv"));
		const privateEnvFile = path.join(projectDir, ".private.env");
		writeEnvironment(privateEnvFile, remoteEnvironment("private"));

		for (const entry of ["default .env", "explicit private --env-file"]) {
			for (const shellOverrides of [false, true]) {
				await t.test(`${entry}, ${shellOverrides ? "remote shell takes precedence" : "env-file only"}`, () => {
					const explicit = entry === "explicit private --env-file";
					const environment = dockerEnvironment();
					if (shellOverrides) Object.assign(environment, remoteEnvironment("shell"));
					const config = composeConfig(projectDir, explicit ? privateEnvFile : null, environment);
					const source = shellOverrides ? "shell" : explicit ? "private" : "dotenv";
					assert.ok(config.services?.["waygate-api"]?.environment?.WAYGATE_CALLBACK_BASE_URL === `https://${source}.invalid/callback`, "Compose must load the selected synthetic env input with shell precedence");

					const incorrectServices = Object.entries(expectedDatabases)
						.filter(([name, expected]) => config.services?.[name]?.environment?.DATABASE_URL !== expected)
						.map(([name]) => name);
					assert.ok(incorrectServices.length === 0, `DATABASE_URL must retain its literal local driver, user, password, DB host, port and schema for: ${incorrectServices.join(", ")} (rendered values withheld)`);
				});
			}
		}
	} finally {
		fs.rmSync(tempDir, { recursive: true, force: true });
	}
});
