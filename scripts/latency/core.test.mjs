import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import * as core from './core.mjs';

test('percentiles interpolate linearly and summaries ignore non-finite samples', () => {
	assert.equal(core.percentile([10, 20, 30, 40, 50], 50), 30);
	assert.equal(core.percentile([10, 20, 30, 40, 50], 90), 46);
	const summary = core.summarize([50, NaN, 10, 30, 20, 40, undefined]);
	assert.equal(summary.count, 5);
	assert.equal(summary.min, 10);
	assert.equal(summary.p50, 30);
	assert.equal(summary.max, 50);
	assert.deepEqual(core.summarize([NaN]), { count: 0 });
});

test('route inventory maps page files to URL patterns and ignores layout-only folders', () => {
	const root = mkdtempSync(join(tmpdir(), 'latency-routes-'));
	try {
		for (const dir of ['a', '(app)/b/[id]', 'c/[[opt]]', 'd/[...rest]', 'layout-only']) mkdirSync(join(root, dir), { recursive: true });
		for (const file of ['+page.svelte', 'a/+page.svelte', '(app)/b/[id]/+page.svelte', 'c/[[opt]]/+page.svelte', 'd/[...rest]/+page.svelte', 'layout-only/+layout.svelte']) {
			writeFileSync(join(root, file), '');
		}
		assert.deepEqual(core.listPageRoutes(root).map((r) => r.pattern), ['/', '/a', '/b/[id]', '/c/[[opt]]', '/d/[...rest]']);
	} finally {
		rmSync(root, { recursive: true, force: true });
	}
});

test('route patterns match concrete paths for their parameter shape', () => {
	assert.ok(core.routeRegExp('/b/[id]').test('/b/x1'));
	assert.ok(!core.routeRegExp('/b/[id]').test('/b'));
	assert.ok(!core.routeRegExp('/b/[id]').test('/b/x/y'));
	assert.ok(core.routeRegExp('/c/[[opt]]').test('/c'));
	assert.ok(core.routeRegExp('/c/[[opt]]').test('/c/x'));
	assert.ok(core.routeRegExp('/d/[...rest]').test('/d/x/y'));
	assert.ok(!core.routeRegExp('/dashboard').test('/dashboard/extra'));
});

const routes = [
	{ pattern: '/', file: '+page.svelte' },
	{ pattern: '/dashboard', file: 'dashboard/+page.svelte' },
	{ pattern: '/b/[id]', file: 'b/[id]/+page.svelte' },
	{ pattern: '/logout', file: 'logout/+page.svelte' },
	{ pattern: '/c/[slug]', file: 'c/[slug]/+page.svelte' }
];

test('route plan accounts for every route: measured plus skipped equals the inventory', () => {
	const plan = core.planRoutes(routes, { fixtures: { '/b/[id]': '/b/42' } });
	assert.equal(plan.total, routes.length);
	assert.deepEqual(plan.measured.map((r) => r.path), ['/', '/dashboard', '/b/42']);
	assert.equal(plan.measured.length + plan.skipped.length, plan.total);
	assert.match(plan.skipped.find((s) => s.pattern === '/logout').reason, /session-destructive/);
	assert.match(plan.skipped.find((s) => s.pattern === '/c/[slug]').reason, /without a --route-fixtures entry/);
});

test('route plan rejects a fixture that does not belong to its route', () => {
	assert.throws(() => core.planRoutes(routes, { fixtures: { '/b/[id]': '/other/42' } }), /does not match that route/);
});

test('route filter skips non-matching routes with an explicit reason', () => {
	const plan = core.planRoutes(routes, { filter: /^\/dashboard$/ });
	assert.deepEqual(plan.measured.map((r) => r.pattern), ['/dashboard']);
	assert.equal(plan.skipped.find((s) => s.pattern === '/').reason, 'excluded by --route-filter');
	assert.equal(plan.measured.length + plan.skipped.length, plan.total);
});
test('dynamic routes can be harvested from discovered on-page links', () => {
	const initialPlan = core.planRoutes(routes, {});
	assert.equal(initialPlan.measured.length, 2); // / and /dashboard
	assert.equal(initialPlan.skipped.length, 3);
	const harvested = core.harvestDynamicRoutes(initialPlan, ['/b/item-99', '/unrelated/path']);
	assert.equal(harvested.total, initialPlan.total);
	assert.equal(harvested.measured.length, 3);
	assert.equal(harvested.newlyMeasured.length, 1);
	assert.equal(harvested.newlyMeasured[0].pattern, '/b/[id]');
	assert.equal(harvested.newlyMeasured[0].path, '/b/item-99');
	assert.equal(harvested.measured.length + harvested.skipped.length, harvested.total);
	const remainingSkippedDynamic = harvested.skipped.find((s) => s.pattern === '/c/[slug]');
	assert.equal(remainingSkippedDynamic.reason, 'dynamic route without fixture or on-page links');
});


test('endpoint keys template opaque identifiers and drop query strings', () => {
	assert.equal(
		core.endpointKey('get', 'http://x/api/v1/instances/3f2a9c1e-1111-4222-8333-944455556666/metrics?token=abc'),
		'GET /api/v1/instances/:id/metrics'
	);
	assert.equal(core.endpointKey('GET', 'http://x/api/v1/volumes/12345'), 'GET /api/v1/volumes/:id');
	assert.equal(core.endpointKey('GET', 'http://x/api/v1/auth/me'), 'GET /api/v1/auth/me');
});

test('recorded URLs lose userinfo, fragments and credential-like query values', () => {
	const redacted = core.redactUrl('http://user:pw@127.0.0.1:3080/x?token=abc&page=2#frag');
	assert.ok(!redacted.includes('abc'));
	assert.ok(!redacted.includes('user:pw'));
	assert.ok(!redacted.includes('#frag'));
	assert.ok(redacted.includes('page=2'));
});

test('targets must be HTTP(S) without credentials, and remote hosts need an explicit allow', () => {
	assert.equal(core.assertTargetAllowed('http://127.0.0.1:3080/some/path'), 'http://127.0.0.1:3080');
	assert.equal(core.assertTargetAllowed('http://192.168.10.5:8000'), 'http://192.168.10.5:8000');
	assert.throws(() => core.assertTargetAllowed('https://example.com'), /Refusing https:\/\/example\.com/);
	assert.equal(core.assertTargetAllowed('https://example.com/app', { allowRemote: ['https://example.com/'] }), 'https://example.com');
	assert.throws(() => core.assertTargetAllowed('https://user:pw@127.0.0.1'), /must not embed credentials/);
	assert.throws(() => core.assertTargetAllowed('ftp://127.0.0.1'), /http or https/);
	assert.throws(() => core.assertTargetAllowed('not a url'), /not an absolute URL/);
});

test('the harness only reads, plus its own sign-in and sign-out', () => {
	for (const [method, path] of [['GET', '/api/v1/instances'], ['HEAD', '/api/v1/instances'], ['POST', '/api/v1/auth/login'], ['POST', '/api/v1/auth/logout']]) {
		assert.doesNotThrow(() => core.assertMethodAllowed(method, path));
	}
	for (const [method, path] of [['POST', '/api/v1/instances'], ['DELETE', '/api/v1/auth/logout'], ['PUT', '/api/v1/auth/login'], ['PATCH', '/api/v1/volumes/1']]) {
		assert.throws(() => core.assertMethodAllowed(method, path), /refused/);
	}
});
