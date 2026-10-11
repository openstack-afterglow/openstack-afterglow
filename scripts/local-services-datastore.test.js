const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const manifestNames = ["docker-compose.dev.yml", "docker-compose.prod.yml", "docker-compose.yml"];
// This ownership contract is independent of the manifest's anchors/implementation.
const applications = [
	{
		variable: "AFTERGLOW_DATABASE_URL",
		local: "mysql+aiomysql://afterglow:dev@afterglow-mariadb:3306/afterglow",
		consumers: ["backend", "notion-worker"],
	},
	...["waygate", "drover", "lumen", "palimpsest"].map((service) => ({
		variable: `${service.toUpperCase()}_DATABASE_URL`,
		local: `mysql+${service === "palimpsest" ? "asyncmy" : "aiomysql"}://${service}:dev@service-mariadb:3306/${service}`,
		consumers: [`${service}-api`, `${service}-worker`, `${service}-${service === "palimpsest" ? "bootstrap" : "migrate"}`],
	})),
];

function externalEnvironment(source) {
	return Object.fromEntries(applications.map(({ variable }) => [
		variable,
		`mysql+${variable === "PALIMPSEST_DATABASE_URL" ? "asyncmy" : "aiomysql"}://${source}_user:synthetic%24password@${source}.invalid:3308/${variable.toLowerCase()}?charset=utf8mb4`,
	]));
}

function writeEnvironment(filePath, environment) {
	// Single quotes keep synthetic URLs literal, just as an operator env-file does.
	fs.writeFileSync(filePath, Object.entries(environment).map(([key, value]) => `${key}='${value}'\n`).join(""), { mode: 0o600 });
}

function dockerEnvironment() {
	// Keep CLI discovery/configuration, but never inherit app secrets or COMPOSE_* inputs.
	const environment = {};
	for (const key of ["PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SystemRoot", "WINDIR", "DOCKER_CONFIG"]) {
		if (process.env[key] !== undefined) environment[key] = process.env[key];
	}
	return environment;
}

function composeConfig(projectDir, { manifest = "docker-compose.dev.yml", envFile, shell = {}, reject = false } = {}) {
	const args = ["compose", "-f", manifest];
	const profiles = manifest === "docker-compose.dev.yml"
		? ["notion-worker"]
		: manifest === "docker-compose.prod.yml" ? ["notion", "waygate", "drover", "lumen", "palimpsest"] : [];
	for (const profile of profiles) args.push("--profile", profile);
	if (envFile) args.push("--env-file", envFile);
	args.push("config", "--format", "json");
	const result = spawnSync("docker", args, {
		cwd: projectDir,
		env: { ...dockerEnvironment(), ...shell },
		encoding: "utf8",
		stdio: ["ignore", "pipe", "pipe"],
		timeout: 15000,
		killSignal: "SIGKILL",
		maxBuffer: 4 * 1024 * 1024,
	});
	// Never attach stdout/stderr or compare URL strings with assert.equal: rendered
	// configuration and automatic assertion diffs can expose credential values.
	assert.ok(!result.error, `docker compose config could not run (${result.error?.code ?? "unknown"}); Docker Compose is required`);
	assert.ok(result.signal === null, "docker compose config terminated unexpectedly (output withheld)");
	if (reject) {
		assert.ok(result.status !== 0, "Compose must reject missing or empty AFTERGLOW_DATABASE_URL even when generic DATABASE_URL is supplied");
		return;
	}
	assert.ok(result.status === 0, `docker compose config failed (exit ${result.status}; output withheld)`);
	try {
		return JSON.parse(result.stdout);
	} catch {
		assert.fail("docker compose config did not return valid JSON (output withheld)");
	}
}

function assertDatabases(config, selected, targets = applications, localFallback = true) {
	const incorrect = [];
	for (const { variable, local, consumers } of targets) {
		const expected = localFallback ? selected[variable] || local : selected[variable];
		for (const service of consumers) {
			if (config.services?.[service]?.environment?.DATABASE_URL !== expected) incorrect.push(service);
		}
	}
	assert.ok(incorrect.length === 0, `Incorrect DATABASE_URL destination for: ${incorrect.join(", ")} (rendered values withheld)`);
}

async function withProject(callback) {
	const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "afterglow-datastore-"));
	try {
		const projectDir = path.join(tempDir, "afterglow");
		fs.mkdirSync(projectDir);
		// Copy, never symlink: .env, mounts and sibling contexts must resolve in the
		// temporary synthetic project, not the checkout or its real private inputs.
		for (const manifest of manifestNames) {
			fs.copyFileSync(path.resolve(__dirname, "..", manifest), path.join(projectDir, manifest));
		}
		for (const sibling of ["waygate", "drover", "lumen", "palimpsest"]) fs.mkdirSync(path.join(tempDir, sibling));
		fs.mkdirSync(path.join(projectDir, "tls"));
		await callback(projectDir);
	} finally {
		fs.rmSync(tempDir, { recursive: true, force: true });
	}
}

test("development Compose selects only the named application's database across all 14 consumers", async (t) => {
	await withProject(async (projectDir) => {
		const dotenvPath = path.join(projectDir, ".env");
		const privateEnvFile = path.join(projectDir, ".private.env");
		const dotenv = externalEnvironment("dotenv");
		const privateValues = externalEnvironment("private");
		const shell = externalEnvironment("shell");
		const generic = { DATABASE_URL: "mysql+aiomysql://generic:synthetic@generic.invalid:3306/wrong" };
		const empty = Object.fromEntries(applications.map(({ variable }) => [variable, ""]));
		const run = async (name, dotenvValues, privateInputs, shellInputs, expected) => {
			await t.test(name, () => {
				writeEnvironment(dotenvPath, dotenvValues);
				if (privateInputs !== null) writeEnvironment(privateEnvFile, privateInputs);
				const config = composeConfig(projectDir, { envFile: privateInputs === null ? null : privateEnvFile, shell: shellInputs });
				assertDatabases(config, expected);
			});
		};

		await t.test("unset variables and absent .env retain local defaults", () => {
			assertDatabases(composeConfig(projectDir), {});
		});
		await run("generic DATABASE_URL cannot redirect the development stack", generic, null, generic, {});
		await run("empty prefixed .env values retain local defaults", { ...generic, ...empty }, null, {}, {});
		await run("empty explicit env-file does not inherit .env destinations", dotenv, { ...generic, ...empty }, {}, {});

		for (const { variable } of applications) {
			await run(`${variable} .env override is isolated`, { ...generic, [variable]: dotenv[variable] }, null, {}, { [variable]: dotenv[variable] });
			await run(`${variable} explicit env-file override is isolated`, generic, { ...generic, [variable]: privateValues[variable] }, {}, { [variable]: privateValues[variable] });
			await run(`${variable} shell override is isolated`, generic, null, { ...generic, [variable]: shell[variable] }, { [variable]: shell[variable] });
		}

		for (const explicit of [false, true]) {
			const entry = explicit ? "explicit env-file" : "default .env";
			const selected = explicit ? privateValues : dotenv;
			await run(`${entry} selects all five distinct destinations`, { ...generic, ...dotenv }, explicit ? { ...generic, ...privateValues } : null, {}, selected);
			await run(`${entry} yields to all shell destinations`, { ...generic, ...dotenv }, explicit ? privateValues : null, { ...generic, ...shell }, shell);
			await run(`${entry} empty shell values use local defaults, not env-file values`, dotenv, explicit ? privateValues : null, empty, {});
			for (const { variable } of applications) {
				await run(`${entry} partial shell ${variable} overrides only its consumers`, dotenv, explicit ? privateValues : null, { [variable]: shell[variable] }, { ...selected, [variable]: shell[variable] });
				await run(`${entry} empty shell ${variable} falls back only its consumers`, dotenv, explicit ? privateValues : null, { [variable]: "" }, { ...selected, [variable]: "" });
			}
		}
	});
});

test("production and standalone Compose require the prefixed Afterglow input without a generic alias", async (t) => {
	await withProject(async (projectDir) => {
		const dotenvPath = path.join(projectDir, ".env");
		const privateEnvFile = path.join(projectDir, ".private.env");
		const dotenv = externalEnvironment("dotenv");
		const privateValues = externalEnvironment("private");
		const shell = externalEnvironment("shell");
		const required = {
			SECRET_KEY: "synthetic-secret-key-not-used-by-any-application",
			OS_PASSWORD: "synthetic-keystone-password",
			ORIGIN: "https://frontend.invalid",
			PUBLIC_API_BASE: "https://api.invalid",
			TLS_CERTS_DIR: path.join(projectDir, "tls"),
			REDIS_URL: "redis://synthetic-redis.invalid:6379/0",
			DATABASE_URL: "mysql+aiomysql://generic:synthetic@generic.invalid:3306/wrong",
		};

		for (const manifest of ["docker-compose.prod.yml", "docker-compose.yml"]) {
			const targets = manifest === "docker-compose.prod.yml"
				? applications : [{ ...applications[0], consumers: ["backend"] }];
			const run = async (name, dotenvValues, privateInputs, shellInputs, expected, reject = false) => {
				await t.test(`${manifest}: ${name}`, () => {
					writeEnvironment(dotenvPath, { ...required, ...dotenvValues });
					if (privateInputs !== null) writeEnvironment(privateEnvFile, { ...required, ...privateInputs });
					const config = composeConfig(projectDir, { manifest, envFile: privateInputs === null ? null : privateEnvFile, shell: shellInputs, reject });
					if (!reject) assertDatabases(config, expected, targets, false);
				});
			};

			await run(".env selects the prefixed database rather than generic DATABASE_URL", dotenv, null, {}, dotenv);
			await run("explicit private env-file replaces .env destinations", dotenv, privateValues, {}, privateValues);
			await run("shell overrides default .env", dotenv, null, shell, shell);
			await run("shell overrides private env-file", dotenv, privateValues, shell, shell);
			await run("missing .env prefixed input is rejected despite generic input", {}, null, {}, {}, true);
			await run("empty .env prefixed input is rejected despite generic input", { AFTERGLOW_DATABASE_URL: "" }, null, {}, {}, true);
			await run("missing private input cannot inherit valid .env input", dotenv, {}, {}, {}, true);
			await run("empty private input cannot inherit valid .env input", dotenv, { AFTERGLOW_DATABASE_URL: "" }, {}, {}, true);
			await run("empty shell cannot inherit valid .env input", dotenv, null, { AFTERGLOW_DATABASE_URL: "" }, {}, true);
			await run("empty shell cannot inherit valid private input", dotenv, privateValues, { AFTERGLOW_DATABASE_URL: "" }, {}, true);
		}
	});
});
