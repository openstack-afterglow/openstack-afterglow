#!/usr/bin/env node
const path = require("node:path");
const { devNull } = require("node:os");
const { spawnSync } = require("node:child_process");

const rootDir = path.resolve(__dirname, "..");
const testTargetPath = path.join(__dirname, "test-target.js");
const composeFile = path.join(rootDir, "docker-compose.dev.yml");
const projectName = process.env.AFTERGLOW_TEST_PROJECT_NAME || "afterglow-test";
const services = ["mariadb", "postgres", "test-redis"];

const localDatabaseUrl = "mysql+aiomysql://afterglow:dev@127.0.0.1:3307/afterglow_functional";
const localCheckpointerUrl = "postgresql://afterglow:dev@127.0.0.1:5434/afterglow_checkpoints";
const localRedisUrl = "redis://127.0.0.1:6380/0";

function run(command, args, options = {}) {
	const result = spawnSync(command, args, {
		cwd: rootDir,
		stdio: "inherit",
		...options
	});
	if (result.error) {
		console.error(result.error.message);
		return 1;
	}
	return result.status === null ? 1 : result.status;
}

function composeArgs(...args) {
	return ["compose", "--env-file", devNull, "-f", composeFile, "-p", projectName, "--profile", "test", ...args];
}

function main(argv, runner = run) {
	const noStart = argv.includes("--no-start");
	const keep = argv.includes("--keep");
	const targetArgs = argv.filter((arg) => arg !== "--no-start" && arg !== "--keep");
	const ownsServices = !noStart && !process.env.AFTERGLOW_TEST_DATABASE_URL;
	const databaseUrl = process.env.AFTERGLOW_TEST_DATABASE_URL || localDatabaseUrl;
	const checkpointerUrl = process.env.AFTERGLOW_TEST_CHECKPOINTER_POSTGRES_URL || localCheckpointerUrl;
	const redisUrl = process.env.REDIS_URL || process.env.AFTERGLOW_REDIS_URL || localRedisUrl;
	let exitCode = 0;

	try {
		if (ownsServices) {
			console.log("Starting disposable MariaDB, PostgreSQL, and Redis functional services...");
			exitCode = runner("docker", composeArgs("up", "-d", "--wait", "--no-deps", ...services));
		}

		if (exitCode === 0) {
			console.log(`Running functional tests against ${databaseUrl.replace(/:[^:@/]+@/, ":***@")}`);
			exitCode = runner(process.execPath, [testTargetPath, "db", ...targetArgs], {
				env: {
					...process.env,
					AFTERGLOW_TEST_DATABASE_URL: databaseUrl,
					AFTERGLOW_TEST_CHECKPOINTER_POSTGRES_URL: checkpointerUrl,
					AFTERGLOW_TEST_REAL_REDIS: "1",
					REDIS_URL: redisUrl,
					AFTERGLOW_REDIS_URL: redisUrl
				}
			});
		}
	} finally {
		if (ownsServices && !keep) {
			console.log("Tearing down disposable functional services...");
			const downExitCode = runner("docker", composeArgs("down", ...services));
			if (exitCode === 0 && downExitCode !== 0) exitCode = downExitCode;
		}
	}

	return exitCode;
}

if (require.main === module) {
	process.exit(main(process.argv.slice(2)));
}

module.exports = {
	composeArgs,
	composeFile,
	localCheckpointerUrl,
	localDatabaseUrl,
	localRedisUrl,
	main,
	projectName,
	run
};
