import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { setTimeout as delay } from 'node:timers/promises';
import { discoverGetEndpoints, measureAuth, measureEndpoints, signIn, signOut, timedRequest } from './api-lane.mjs';

// Loopback fixture backend with controllable latencies. Its timings are the ground truth the lane must reproduce.
const state = { loginDelayMs: 0, slowMs: 200, requests: [], tokens: new Set(), counter: 0, revokeOnSecondSlow: null };
let server;
let base;

function json(res, status, body) {
	res.writeHead(status, { 'content-type': 'application/json' });
	res.end(JSON.stringify(body));
}

before(async () => {
	server = http.createServer(async (req, res) => {
		for await (const _chunk of req) {
			// drain request bodies so keep-alive connections stay usable
		}
		const url = new URL(req.url, 'http://fixture.invalid');
		const auth = req.headers.authorization ?? '';
		const token = auth.startsWith('Bearer ') ? auth.slice(7) : null;
		state.requests.push({ method: req.method, path: url.pathname, authorized: Boolean(token && state.tokens.has(token)), project: req.headers['x-project-id'] ?? null });
		if (req.method === 'POST' && url.pathname === '/api/v1/auth/login') {
			await delay(state.loginDelayMs);
			const newToken = `tok-${++state.counter}`;
			state.tokens.add(newToken);
			return json(res, 200, { token: newToken, project_id: 'project-1', refresh_token: 'r-fixture' });
		}
		if (req.method === 'POST' && url.pathname === '/api/v1/auth/logout') {
			if (token) state.tokens.delete(token);
			return json(res, 200, {});
		}
		if (req.method === 'GET' && url.pathname === '/api/v1/auth/me') {
			return token && state.tokens.has(token) ? json(res, 200, { user: 'fixture' }) : json(res, 401, { detail: 'no' });
		}
		if (req.method === 'GET' && url.pathname === '/api/v1/fast') {
			res.setHeader('server-timing', 'app;dur=12.5');
			return json(res, 200, { ok: true });
		}
		if (req.method === 'GET' && url.pathname === '/api/v1/slow') {
			// Deterministic mid-run revocation: the token dies exactly when the second slow request arrives.
			if (state.revokeOnSecondSlow && state.requests.filter((r) => r.path === '/api/v1/slow').length >= 2) state.tokens.delete(state.revokeOnSecondSlow);
			await delay(state.slowMs);
			return json(res, 200, { ok: true });
		}
		if (req.method === 'GET' && url.pathname === '/api/v1/protected') {
			return token && state.tokens.has(token) ? json(res, 200, { ok: true }) : json(res, 401, { detail: 'no' });
		}
		if (req.method === 'GET' && url.pathname === '/api/v1/boom') return json(res, 500, { detail: 'boom' });
		if (req.method === 'GET' && url.pathname === '/api/v1/events') {
			res.writeHead(200, { 'content-type': 'text/event-stream' });
			res.write('data: hello\n\n');
			req.on('close', () => res.end());
			return;
		}
		if (req.method === 'GET' && url.pathname === '/openapi.json') {
			return json(res, 200, {
				paths: {
					'/api/v1/fast': { get: { operationId: 'fast' } },
					'/api/v1/slow': { get: { operationId: 'slow' } },
					'/api/v1/items/{id}': { get: { operationId: 'item' } },
					'/api/v1/auth/logout': { post: { operationId: 'logout' } }
				}
			});
		}
		return json(res, 404, { detail: 'not found' });
	});
	await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
	base = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
	await new Promise((resolve) => server.close(resolve));
});

const creds = () => ({ username: 'fixture-user', password: 'fixture-pass' });
const reset = () => {
	state.loginDelayMs = 0;
	state.slowMs = 200;
	state.revokeOnSecondSlow = null;
	state.requests.length = 0;
};

test('sign-in latency is not counted in endpoint samples', async () => {
	reset();
	state.loginDelayMs = 300;
	const session = await signIn({ apiBase: base, ...creds() });
	assert.ok(session.loginMs >= 250, `login measured ${session.loginMs}ms`);
	const { perEndpoint } = await measureEndpoints({
		apiBase: base,
		token: session.token,
		projectId: session.projectId,
		endpoints: [{ method: 'GET', path: '/api/v1/fast' }],
		samples: 5,
		levels: [1],
		rounds: 1
	});
	assert.ok(perEndpoint[0].total_ms.p50 < 150, `fast endpoint p50 ${perEndpoint[0].total_ms.p50}ms includes login`);
	await signOut({ apiBase: base, token: session.token });
});

test('concurrent requests overlap rather than queueing behind each other', async () => {
	reset();
	const session = await signIn({ apiBase: base, ...creds() });
	const { ramp } = await measureEndpoints({
		apiBase: base,
		token: session.token,
		projectId: session.projectId,
		endpoints: [{ method: 'GET', path: '/api/v1/slow' }],
		samples: 1,
		levels: [10],
		rounds: 2
	});
	const [level] = ramp;
	assert.equal(level.requests, 20);
	// Ten 200ms requests in series would take ~2000ms per batch; overlapped they take roughly one request time.
	assert.ok(level.batch_wall_ms.p50 < 1000, `batch wall p50 ${level.batch_wall_ms.p50}ms looks serialized`);
	assert.ok(level.request_ms.p50 >= 180, `request p50 ${level.request_ms.p50}ms is shorter than the server delay`);
	await signOut({ apiBase: base, token: session.token });
});

test('a mixed batch spreads concurrent requests across the selected endpoints', async () => {
	reset();
	const session = await signIn({ apiBase: base, ...creds() });
	try {
		// samples: 0 isolates the batch: only the round-robin calls reach the server.
		await measureEndpoints({
			apiBase: base,
			token: session.token,
			projectId: session.projectId,
			endpoints: [{ method: 'GET', path: '/api/v1/fast' }, { method: 'GET', path: '/api/v1/slow' }],
			samples: 0,
			levels: [4],
			rounds: 1
		});
		const seen = state.requests.filter((r) => r.path === '/api/v1/fast' || r.path === '/api/v1/slow').map((r) => r.path);
		assert.equal(seen.filter((p) => p === '/api/v1/fast').length, 2);
		assert.equal(seen.filter((p) => p === '/api/v1/slow').length, 2);
	} finally {
		await signOut({ apiBase: base, token: session.token });
	}
});

test('event streams are timed to their headers and then cancelled', async () => {
	const result = await timedRequest(`${base}/api/v1/events`, { headers: { Accept: 'text/event-stream' }, timeoutMs: 5000 });
	assert.equal(result.kind, 'stream');
	assert.equal(result.status, 200);
	assert.ok(result.totalMs < 1000, `stream held the request open for ${result.totalMs}ms`);
});

test('Server-Timing dur= is parsed from response headers into serverDurMs', async () => {
	const result = await timedRequest(`${base}/api/v1/fast`);
	assert.equal(result.serverDurMs, 12.5);
});

test('server errors are counted by status and do not abort the measurement', async () => {
	reset();
	const session = await signIn({ apiBase: base, ...creds() });
	const { perEndpoint } = await measureEndpoints({
		apiBase: base,
		token: session.token,
		projectId: session.projectId,
		endpoints: [{ method: 'GET', path: '/api/v1/boom' }],
		samples: 3,
		levels: [1],
		rounds: 1
	});
	assert.deepEqual(perEndpoint[0].status_counts, { 500: 3 });
	await signOut({ apiBase: base, token: session.token });
});

test('the auth probe reports sign-in plus the first request as one cold-path figure', async () => {
	reset();
	state.loginDelayMs = 200;
	const auth = await measureAuth({ apiBase: base, ...creds(), samples: 2, probe: '/api/v1/fast' });
	assert.ok(auth.login_ms.p50 >= 180, `login p50 ${auth.login_ms.p50}ms`);
	assert.ok(auth.login_plus_probe_ms.p50 >= auth.login_ms.p50, 'cold path must include the sign-in');
	assert.ok(auth.probe.total_ms.p50 < auth.login_plus_probe_ms.p50 - 150, 'probe time must not absorb the sign-in');
	// Each sample signs out again, so no fixture session survives the measurement.
	assert.equal(state.tokens.size, 0);
});

test('the sign-in budget stays below the backend rate limit', async () => {
	await assert.rejects(measureAuth({ apiBase: 'http://127.0.0.1:1', ...creds(), samples: 10 }), /below 10/);
});

test('project scope is forwarded with the token on measured requests', async () => {
	reset();
	const session = await signIn({ apiBase: base, ...creds() });
	await measureEndpoints({ apiBase: base, token: session.token, projectId: session.projectId, endpoints: [{ method: 'GET', path: '/api/v1/fast' }], samples: 1, levels: [1], rounds: 1 });
	const measured = state.requests.filter((r) => r.path === '/api/v1/fast');
	assert.ok(measured.length > 0);
	assert.ok(measured.every((r) => r.project === 'project-1'));
	await signOut({ apiBase: base, token: session.token });
});

test('endpoint discovery skips parameterised paths explicitly and honours filters', () => {
	const openapi = {
		paths: {
			'/api/v1/fast': { get: {} },
			'/api/v1/slow': { get: {} },
			'/api/v1/items/{id}': { get: {} },
			'/api/v1/auth/logout': { post: {} }
		}
	};
	const all = discoverGetEndpoints(openapi);
	assert.deepEqual(all.measurable.map((e) => e.path), ['/api/v1/fast', '/api/v1/slow']);
	assert.deepEqual(all.skipped, [{ path: '/api/v1/items/{id}', reason: 'path parameters need a concrete value' }]);
	assert.deepEqual(discoverGetEndpoints(openapi, { include: /fast/ }).measurable.map((e) => e.path), ['/api/v1/fast']);
	assert.deepEqual(discoverGetEndpoints(openapi, { exclude: /slow/, max: 5 }).measurable.map((e) => e.path), ['/api/v1/fast']);
	assert.equal(discoverGetEndpoints(openapi, { max: 1 }).truncated, 1);
});

test('the request primitive refuses writes outside the session policy before sending them', async () => {
	reset();
	await assert.rejects(timedRequest(`${base}/api/v1/fast`, { method: 'DELETE' }), /refused/);
	assert.equal(state.requests.length, 0);
});

test('a token rejected mid-run aborts instead of recording 401s as latency', async () => {
	reset();
	const session = await signIn({ apiBase: base, ...creds() });
	// /protected is the second endpoint: the token is revoked once the first endpoint's samples are done.
	state.revokeOnSecondSlow = session.token;
	state.slowMs = 20;
	try {
		const result = await measureEndpoints({
			apiBase: base,
			token: session.token,
			projectId: session.projectId,
			endpoints: [
				{ method: 'GET', path: '/api/v1/slow' },
				{ method: 'GET', path: '/api/v1/protected' },
				{ method: 'GET', path: '/api/v1/fast' }
			],
			samples: 2,
			levels: [3],
			rounds: 1
		});
		assert.equal(result.aborted?.reason, 'auth_rejected');
		assert.equal(result.aborted.stage, 'endpoints');
		assert.equal(result.aborted.endpoint, 'GET /api/v1/protected');
		const protectedRow = result.perEndpoint.find((e) => e.endpoint === 'GET /api/v1/protected');
		assert.equal(protectedRow.invalid, 'auth_rejected');
		assert.equal(protectedRow.total_ms.count, 0, '401 responses must not contribute latency samples');
		assert.equal(result.perEndpoint.some((e) => e.endpoint === 'GET /api/v1/fast'), false, 'measuring must stop at the rejection');
		assert.deepEqual(result.ramp, [], 'the ramp must not run on a rejected token');
	} finally {
		state.revokeOnSecondSlow = null;
	}
});

test('an already expired token is detected before any endpoint is measured', async () => {
	reset();
	const result = await measureEndpoints({
		apiBase: base,
		token: 'expired',
		endpoints: [{ method: 'GET', path: '/api/v1/protected' }],
		samples: 3,
		levels: [2],
		rounds: 1
	});
	assert.equal(result.aborted?.stage, 'preflight');
	assert.deepEqual(result.perEndpoint, []);
	assert.equal(state.requests.filter((r) => r.path === '/api/v1/protected').length, 0);
});

test('refreshAuth renews a rejected token once, even when concurrent requests hit 401 together', async () => {
	reset();
	let refreshes = 0;
	const result = await measureEndpoints({
		apiBase: base,
		token: 'expired',
		endpoints: [{ method: 'GET', path: '/api/v1/protected' }],
		samples: 2,
		levels: [5],
		rounds: 1,
		refreshAuth: async () => {
			refreshes++;
			return signIn({ apiBase: base, ...creds() });
		}
	});
	assert.equal(result.aborted, null);
	assert.equal(refreshes, 1, 'one login must serve every request that saw the expired token');
	assert.deepEqual(result.perEndpoint[0].status_counts, { 200: 2 });
	assert.deepEqual(result.ramp[0].status_counts, { 200: 5 });
});
