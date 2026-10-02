import { setTimeout as delay } from 'node:timers/promises';

export function check(condition, message) {
	if (!condition) throw new Error(message);
}

export function required(env, name) {
	const value = env[name]?.trim();
	check(value, `${name} is required; credentials belong in environment variables, not command arguments.`);
	return value;
}

export function serviceOrigin(value) {
	let url;
	try { url = new URL(value); } catch { throw new Error('Service URL must be an absolute HTTP(S) origin or /v1 API base.'); }
	check(['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !url.search && !url.hash,
		'Service URL must use HTTP(S) without credentials, query or fragment.');
	check(['', '/', '/v1', '/v1/'].includes(url.pathname), 'Service URL must be an origin or /v1 API base.');
	return url.origin;
}

export function createClient({ url, headers, timeout = 30_000 }) {
	const origin = serviceOrigin(url);
	return {
		origin,
		async request(path, { method = 'GET', json, body, headers: extra = {}, expected = [200], format = 'json' } = {}) {
			check(path.startsWith('/v1/') || path === '/v1', 'Verifier requests must stay inside the service /v1 API.');
			let response;
			try {
				response = await fetch(`${origin}${path}`, {
					method, redirect: 'error', signal: AbortSignal.timeout(timeout),
					headers: { Accept: 'application/json', ...headers, ...(json === undefined ? {} : { 'Content-Type': 'application/json' }), ...extra },
					body: json === undefined ? body : JSON.stringify(json)
				});
			} catch {
				throw new Error(`${method} ${path.split('?')[0]} could not reach the service within the request deadline (redirects are not followed).`);
			}
			check(expected.includes(response.status), `${method} ${path.split('?')[0]} returned HTTP ${response.status}. Upstream response bodies are not logged.`);
			if (format === 'response') return response;
			if (format === 'empty') { await response.arrayBuffer(); return null; }
			if (format === 'bytes') return Buffer.from(await response.arrayBuffer());
			if (format === 'text') return response.text();
			try { return await response.json(); } catch { throw new Error(`${method} ${path.split('?')[0]} returned invalid JSON.`); }
		}
	};
}

export async function poll(read, finished, { timeout = 120_000, interval = 250, label = 'operation' } = {}) {
	const deadline = Date.now() + timeout;
	do {
		const value = await read();
		if (finished(value)) return value;
		await delay(interval);
	} while (Date.now() < deadline);
	throw new Error(`${label} did not reach its required state within ${timeout / 1000}s.`);
}

// Cleanup failure must fail the verification without hiding the original failure.
export async function withCleanup(work, cleanup) {
	let failure;
	let result;
	try { result = await work(); } catch (error) { failure = error; }
	try { await cleanup(); } catch (error) {
		throw new Error(`${failure ? `${failure.message}; ` : ''}cleanup failed: ${error.message}`);
	}
	if (failure) throw failure;
	return result;
}
