const assert = require("node:assert/strict");
const test = require("node:test");

const { main } = require("./test-db");

const managedEnv = [
	"AFTERGLOW_REDIS_URL",
	"AFTERGLOW_TEST_CHECKPOINTER_POSTGRES_URL",
	"AFTERGLOW_TEST_DATABASE_URL",
	"REDIS_URL"
];

function withCleanEnvironment(callback) {
	const previous = Object.fromEntries(managedEnv.map((name) => [name, process.env[name]]));
	for (const name of managedEnv) delete process.env[name];
	try {
		return callback();
	} finally {
		for (const name of managedEnv) {
			if (previous[name] === undefined) delete process.env[name];
			else process.env[name] = previous[name];
		}
	}
}

function commandCalls(calls, command) {
	return calls.filter((call) => call.command === command);
}

function makeRunner(resultFor = () => 0) {
	const calls = [];
	return {
		calls,
		run(command, args, options) {
			calls.push({ command, args, options });
			return resultFor(command, args, options);
		}
	};
}

test("--no-start reuses services without owning their lifecycle", () =>
	withCleanEnvironment(() => {
		const runner = makeRunner();
		assert.equal(main(["--no-start"], runner.run.bind(runner)), 0);
		assert.equal(commandCalls(runner.calls, "docker").length, 0);

		const targetCall = runner.calls.find((call) => call.command === process.execPath);
		assert.ok(targetCall, "functional target must run");
	}));

test("--keep starts services but intentionally skips teardown", () =>
	withCleanEnvironment(() => {
		const runner = makeRunner();
		assert.equal(main(["--keep"], runner.run.bind(runner)), 0);
		const dockerCalls = commandCalls(runner.calls, "docker");
		assert.ok(dockerCalls.some((call) => call.args.includes("up")));
		assert.ok(!dockerCalls.some((call) => call.args.includes("down")));
	}));

test("auto-started services are torn down after successful tests", () =>
	withCleanEnvironment(() => {
		const runner = makeRunner();
		assert.equal(main([], runner.run.bind(runner)), 0);
		const dockerCalls = commandCalls(runner.calls, "docker");
		assert.ok(dockerCalls.some((call) => call.args.includes("up")));
		const down = dockerCalls.find((call) => call.args.includes("down"));
		assert.ok(down, "owned services must be torn down");
	}));

test("test failure is preserved and still tears down services", () =>
	withCleanEnvironment(() => {
		const runner = makeRunner((command) => (command === process.execPath ? 7 : 0));
		assert.equal(main([], runner.run.bind(runner)), 7);
		assert.ok(commandCalls(runner.calls, "docker").some((call) => call.args.includes("down")));
	}));

test("partial startup failure still triggers teardown", () =>
	withCleanEnvironment(() => {
		const runner = makeRunner((command, args) => (command === "docker" && args.includes("up") ? 9 : 0));
		assert.equal(main([], runner.run.bind(runner)), 9);
		assert.ok(commandCalls(runner.calls, "docker").some((call) => call.args.includes("down")));
		assert.equal(
			runner.calls.some((call) => call.command === process.execPath),
			false
		);
	}));

test("teardown failure fails an otherwise successful run", () =>
	withCleanEnvironment(() => {
		const runner = makeRunner((command, args) => (command === "docker" && args.includes("down") ? 11 : 0));
		assert.equal(main([], runner.run.bind(runner)), 11);
	}));
