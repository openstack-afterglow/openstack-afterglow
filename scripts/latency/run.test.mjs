import { test } from 'node:test';
import assert from 'node:assert/strict';
import { listPageRoutes } from './core.mjs';
import { REPO_ROUTES_DIR, parseOptions, runLatency } from './run.mjs';

test('defaults measure both lanes against the repository route tree', () => {
	const options = parseOptions(['--target', 'http://127.0.0.1:3080'], {});
	assert.deepEqual(options.lanes, ['api', 'browser']);
	assert.equal(options.apiBase, 'http://127.0.0.1:3080');
	assert.equal(options.routesDir, REPO_ROUTES_DIR);
	assert.deepEqual(options.levels, [1, 5, 10, 20]);
	assert.equal(options.authSamples, 5);
});

test('credentials are only read from the environment, never accepted as arguments', () => {
	assert.throws(() => parseOptions(['--target', 'http://127.0.0.1', '--password', 'secret'], {}), /Unknown option/);
	assert.throws(() => parseOptions(['--target', 'http://127.0.0.1', '--username', 'me'], {}), /Unknown option/);
});

test('the sign-in budget cannot exceed the backend login rate limit', () => {
	assert.throws(() => parseOptions(['--target', 'http://127.0.0.1', '--auth-samples', '10'], {}), /--auth-samples must be an integer from 1 to 9/);
});

test('unknown lanes and malformed levels are rejected before any request', () => {
	assert.throws(() => parseOptions(['--target', 'http://127.0.0.1', '--lanes', 'api,ui'], {}), /--lanes/);
	assert.throws(() => parseOptions(['--target', 'http://127.0.0.1', '--levels', '1,0'], {}), /--levels/);
});

test('budgets are opt-in and must be positive numbers', () => {
	assert.deepEqual(parseOptions(['--target', 'http://127.0.0.1'], {}).budgets, {});
	assert.deepEqual(parseOptions(['--target', 'http://127.0.0.1', '--budget-ready-p95-ms', '3000'], {}).budgets, { readyP95Ms: 3000 });
	assert.throws(() => parseOptions(['--target', 'http://127.0.0.1', '--budget-api-p95-ms=-1'], {}), /positive number/);
});

test('dry run accounts for every page route of the real frontend without network access', async () => {
	const lines = [];
	const result = await runLatency(parseOptions(['--target', 'http://127.0.0.1:3080', '--dry-run'], {}), { env: {}, log: (line) => lines.push(line) });
	const inventory = listPageRoutes(REPO_ROUTES_DIR);
	assert.equal(result.dryRun, true);
	assert.equal(result.routes.total, inventory.length);
	assert.equal(result.routes.measured.length + result.routes.skipped.length, inventory.length);
	assert.ok(result.routes.measured.length > 0, 'static routes must be measured');
	assert.ok(result.routes.skipped.some((s) => /dynamic route without/.test(s.reason)), 'dynamic routes without fixtures are skipped with a reason');
	assert.ok(lines.some((line) => line.startsWith(`routes: ${inventory.length} page routes`)));
});

test('remote targets are refused before the plan is computed', async () => {
	await assert.rejects(runLatency(parseOptions(['--target', 'https://example.com', '--dry-run'], {}), { env: {}, log: () => {} }), /Refusing https:\/\/example\.com/);
});

test('--interactive permits missing environment credentials and sets interactive mode', () => {
	const options = parseOptions(['--target', 'http://127.0.0.1:3080', '--interactive'], {});
	assert.equal(options.interactive, true);
});
