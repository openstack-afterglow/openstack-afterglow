// API lane: sign-in latency, per-endpoint request latency and concurrent batch completion.
// Every request goes through timedRequest, which enforces the method policy from core.mjs.
import { assertMethodAllowed, check, endpointKey, round, summarize } from './core.mjs';

export const DEFAULT_LEVELS = [1, 5, 10, 20];
export const DEFAULT_PROBE = '/api/v1/auth/me';
// The backend limits /api/v1/auth/login to 10 requests per minute per client (see auth.py).
export const LOGIN_BUDGET_PER_MINUTE = 10;

export function classifyFetchError(error) {
	if (error?.name === 'AbortError' || error?.name === 'TimeoutError') return 'deadline';
	return error?.cause?.code ?? error?.code ?? 'network_error';
}

/**
 * One HTTP exchange timed from issue to the last body byte. Streams (text/event-stream) never
 * finish, so they are timed to the response headers and then cancelled.
 * The returned object holds no request headers, so credentials cannot leak into a report.
 */
export async function timedRequest(url, { method = 'GET', headers = {}, body, timeoutMs = 30000, parseJson = false } = {}) {
	assertMethodAllowed(method, new URL(url).pathname);
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeoutMs);
	const started = performance.now();
	try {
		const response = await fetch(url, { method, headers, body, redirect: 'manual', signal: controller.signal });
		const ttfbMs = performance.now() - started;
		const contentType = response.headers.get('content-type') ?? '';
		const serverTiming = response.headers.get('server-timing') ?? '';
		const durMatch = /dur=([0-9.]+)/.exec(serverTiming);
		const serverDurMs = durMatch ? round(Number(durMatch[1])) : null;
		if (contentType.startsWith('text/event-stream')) {
			await response.body?.cancel().catch(() => {});
			return { status: response.status, kind: 'stream', ttfbMs, totalMs: ttfbMs, serverDurMs, bytes: 0, error: null };
		}
		const buffer = Buffer.from(await response.arrayBuffer());
		const totalMs = performance.now() - started;
		const result = { status: response.status, kind: 'http', ttfbMs, totalMs, serverDurMs, bytes: buffer.byteLength, error: null };
		if (parseJson) {
			try {
				result.json = JSON.parse(buffer.toString('utf8'));
			} catch {
				result.json = undefined;
			}
		}
		return result;
	} catch (error) {
		return { status: null, kind: 'failed', ttfbMs: null, totalMs: performance.now() - started, bytes: 0, error: classifyFetchError(error) };
	} finally {
		clearTimeout(timer);
	}
}

export function authHeaders(token, projectId) {
	return {
		Accept: 'application/json',
		Authorization: `Bearer ${token}`,
		...(projectId ? { 'X-Project-Id': projectId } : {})
	};
}

export async function signIn({ apiBase, username, password, timeoutMs = 30000 }) {
	const result = await timedRequest(`${apiBase}/api/v1/auth/login`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
		body: JSON.stringify({ username, password }),
		timeoutMs,
		parseJson: true
	});
	if (result.status === 429) {
		throw new Error('login rate-limited (HTTP 429): the backend allows 10 logins per minute per client. Wait a minute or lower --auth-samples.');
	}
	if (result.status !== 200) throw new Error(`login failed: HTTP ${result.status ?? result.error}`);
	check(typeof result.json?.token === 'string' && result.json.token.length > 0, 'login succeeded without an access token.');
	return { token: result.json.token, projectId: result.json.project_id || undefined, loginMs: result.totalMs };
}

export async function signOut({ apiBase, token, timeoutMs = 30000 }) {
	const result = await timedRequest(`${apiBase}/api/v1/auth/logout`, {
		method: 'POST',
		headers: authHeaders(token),
		timeoutMs
	});
	return result.status;
}

function statusCounts(results) {
	const counts = {};
	for (const result of results) {
		const key = String(result.status ?? result.error ?? 'failed');
		counts[key] = (counts[key] ?? 0) + 1;
	}
	return counts;
}

function summarizeResults(results) {
	return {
		samples: results.length,
		status_counts: statusCounts(results),
		ttfb_ms: summarize(results.map((r) => r.ttfbMs)),
		total_ms: summarize(results.map((r) => r.totalMs)),
		server_dur_ms: summarize(results.map((r) => r.serverDurMs).filter((v) => v !== null && v !== undefined))
	};
}

/** Endpoints from an OpenAPI document. Paths with parameters need a fixture, so they are skipped explicitly. */
export function discoverGetEndpoints(openapi, { include = null, exclude = null, max = Infinity } = {}) {
	const measurable = [];
	const skipped = [];
	for (const [path, item] of Object.entries(openapi?.paths ?? {})) {
		if (!item?.get) continue;
		if (include && !include.test(path)) continue;
		if (exclude && exclude.test(path)) continue;
		if (/\{[^}]+\}/.test(path)) {
			skipped.push({ path, reason: 'path parameters need a concrete value' });
			continue;
		}
		measurable.push({ method: 'GET', path, operationId: item.get.operationId ?? null });
	}
	const selected = measurable.slice(0, max);
	return { measurable: selected, skipped, truncated: measurable.length - selected.length };
}

/**
 * Warm-path measurements with one token: `samples` sequential requests per endpoint, then a
 * concurrency ramp. A round at level L fires L requests together, spread over the endpoints
 * round-robin, and its batch wall time is the time until every response in that batch has finished.
 *
 * A 401 is never a latency sample: it is the fast path of an expired or revoked token and would
 * make the endpoint look quick. The token is probed before measuring; a rejected token is renewed
 * once through `refreshAuth` (a function returning `{ token, projectId }`) or the lane stops with
 * `aborted` set and reports only what was validly measured.
 */
export async function measureEndpoints({ apiBase, token, projectId, endpoints, samples = 10, levels = DEFAULT_LEVELS, rounds = 3, timeoutMs = 30000, refreshAuth = null, probe = DEFAULT_PROBE }) {
	check(endpoints.length > 0, 'No endpoints to measure.');
	let headers = authHeaders(token, projectId);
	let currentToken = token;
	const urlOf = (endpoint) => `${apiBase}${endpoint.path}`;

	// Single-flight: concurrent 401s share one refresh so a ramp cannot exhaust the login rate limit.
	let renewing = null;
	const renew = () => {
		if (!refreshAuth) return Promise.resolve(false);
		renewing ??= (async () => {
			const next = await refreshAuth();
			if (!next?.token || next.token === currentToken) return false;
			currentToken = next.token;
			headers = authHeaders(next.token, next.projectId ?? projectId);
			return true;
		})().finally(() => {
			renewing = null;
		});
		return renewing;
	};
	const request = async (endpoint) => {
		const usedToken = currentToken;
		const result = await timedRequest(urlOf(endpoint), { headers, timeoutMs });
		if (result.status !== 401) return result;
		// Another request may already have installed a newer token; retry with it without logging in again.
		if (currentToken === usedToken && !(await renew())) return result;
		return timedRequest(urlOf(endpoint), { headers, timeoutMs });
	};

	const preflight = await request({ method: 'GET', path: probe });
	if (preflight.status === 401) {
		return { perEndpoint: [], ramp: [], aborted: { reason: 'auth_rejected', stage: 'preflight', endpoint: null, measured_endpoints: 0 } };
	}

	const perEndpoint = [];
	for (const endpoint of endpoints) {
		const results = [];
		for (let i = 0; i < samples; i++) results.push(await request(endpoint));
		const rejected = results.some((r) => r.status === 401);
		const valid = results.filter((r) => r.status !== 401);
		perEndpoint.push({
			endpoint: endpointKey('GET', urlOf(endpoint)),
			...summarizeResults(valid),
			status_counts: statusCounts(results),
			...(rejected ? { invalid: 'auth_rejected' } : {})
		});
		if (rejected) {
			return { perEndpoint, ramp: [], aborted: { reason: 'auth_rejected', stage: 'endpoints', endpoint: endpointKey('GET', urlOf(endpoint)), measured_endpoints: perEndpoint.length - 1 } };
		}
	}

	const ramp = [];
	for (const level of levels) {
		const requestResults = [];
		const batchWalls = [];
		for (let round = 0; round < rounds; round++) {
			const batch = Array.from({ length: level }, (_, k) => endpoints[(round * level + k) % endpoints.length]);
			const started = performance.now();
			const results = await Promise.all(
				batch.map((endpoint) => request(endpoint).then((result) => ({ ...result, endpoint: endpointKey('GET', urlOf(endpoint)) })))
			);
			batchWalls.push(performance.now() - started);
			requestResults.push(...results);
			if (results.some((r) => r.status === 401)) {
				ramp.push({ concurrency: level, rounds: batchWalls.length, requests: requestResults.length, status_counts: statusCounts(requestResults), invalid: 'auth_rejected' });
				return { perEndpoint, ramp, aborted: { reason: 'auth_rejected', stage: 'ramp', endpoint: null, measured_endpoints: perEndpoint.length } };
			}
		}
		const elapsedMs = batchWalls.reduce((sum, value) => sum + value, 0);
		ramp.push({
			concurrency: level,
			rounds,
			requests: requestResults.length,
			status_counts: statusCounts(requestResults),
			request_ms: summarize(requestResults.map((r) => r.totalMs)),
			batch_wall_ms: summarize(batchWalls),
			throughput_rps: round(requestResults.length / (elapsedMs / 1000), 2)
		});
	}
	return { perEndpoint, ramp, aborted: null };
}

/**
 * Sign-in latency and the auth-included path: each sample logs in, then immediately issues the
 * probe GET with the new token. `login_plus_probe_ms` is what a cold client waits for.
 * Each sample logs out again so sessions do not accumulate.
 */
export async function measureAuth({ apiBase, username, password, samples = 5, probe = DEFAULT_PROBE, timeoutMs = 30000 }) {
	check(Number.isInteger(samples) && samples >= 1, '--auth-samples must be a positive integer.');
	check(samples < LOGIN_BUDGET_PER_MINUTE, `--auth-samples must stay below ${LOGIN_BUDGET_PER_MINUTE} (login rate limit per minute).`);
	const loginMs = [];
	const loginPlusProbeMs = [];
	const probeResults = [];
	for (let i = 0; i < samples; i++) {
		const session = await signIn({ apiBase, username, password, timeoutMs });
		loginMs.push(session.loginMs);
		if (probe) {
			const result = await timedRequest(`${apiBase}${probe}`, { headers: authHeaders(session.token, session.projectId), timeoutMs });
			probeResults.push(result);
			loginPlusProbeMs.push(session.loginMs + result.totalMs);
		}
		await signOut({ apiBase, token: session.token, timeoutMs });
	}
	return {
		samples,
		login_ms: summarize(loginMs),
		probe: probe ? { endpoint: `GET ${probe}`, status_counts: statusCounts(probeResults), total_ms: summarize(probeResults.map((r) => r.totalMs)) } : null,
		login_plus_probe_ms: probe ? summarize(loginPlusProbeMs) : null
	};
}

export async function fetchOpenApi({ apiBase, timeoutMs = 30000 }) {
	const result = await timedRequest(`${apiBase}/openapi.json`, { headers: { Accept: 'application/json' }, timeoutMs, parseJson: true });
	if (result.status !== 200 || !result.json?.paths) {
		throw new Error(`openapi.json unavailable (HTTP ${result.status ?? result.error}). Production disables it; pass --endpoint <path> instead.`);
	}
	return result.json;
}
