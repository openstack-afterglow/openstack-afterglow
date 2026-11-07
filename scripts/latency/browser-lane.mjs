// Browser lane: drives a real Chromium over the DevTools Protocol (no browser-automation
// dependency) and measures each page until it is ready.
//
// Ready = `load` has fired AND no /api/* request is in flight AND none has finished for `quietMs`.
// ready_ms is when the page last settled (load or the last API response), not the end of the quiet
// window. Pages that keep polling never settle; they are reported as not_ready with their API calls.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { check, endpointKey, harvestDynamicRoutes, redactUrl, round } from './core.mjs';

const CHROME_CANDIDATES = {
	darwin: ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium'],
	linux: ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'],
	win32: ['C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe']
};

export function resolveChrome({ env = process.env, platform = process.platform, exists = existsSync } = {}) {
	if (env.AFTERGLOW_LATENCY_CHROME) {
		check(exists(env.AFTERGLOW_LATENCY_CHROME), `AFTERGLOW_LATENCY_CHROME does not exist: ${env.AFTERGLOW_LATENCY_CHROME}`);
		return env.AFTERGLOW_LATENCY_CHROME;
	}
	const found = (CHROME_CANDIDATES[platform] ?? []).find((candidate) => exists(candidate));
	if (!found) throw new Error('Chrome/Chromium not found. Install Chrome or set AFTERGLOW_LATENCY_CHROME to its executable.');
	return found;
}

/** Start an isolated headless Chrome with a temporary profile; `close()` removes both. */
export async function launchChrome(executable, { headless = true, timeoutMs = 20000 } = {}) {
	const userDataDir = await mkdtemp(join(tmpdir(), 'afterglow-latency-'));
	const child = spawn(
		executable,
		[
			...(headless ? ['--headless=new'] : []),
			'--remote-debugging-port=0',
			`--user-data-dir=${userDataDir}`,
			'--no-first-run',
			'--no-default-browser-check',
			'--disable-gpu',
			'--disable-extensions',
			'--remote-allow-origins=*',
			'--window-size=1440,900',
			'about:blank'
		],
		{ stdio: ['ignore', 'ignore', 'pipe'] }
	);
	let stderr = '';
	let wsUrl;
	try {
		wsUrl = await new Promise((resolve, reject) => {
			const timer = setTimeout(() => reject(new Error('Chrome did not expose a DevTools endpoint in time.')), timeoutMs);
			child.stderr.on('data', (chunk) => {
				stderr = (stderr + chunk).slice(-65536);
				const match = /DevTools listening on (ws:\/\/\S+)/.exec(stderr);
				if (match) {
					clearTimeout(timer);
					resolve(match[1]);
				}
			});
			child.once('exit', (code) => {
				clearTimeout(timer);
				reject(new Error(`Chrome exited before DevTools was ready (code ${code}).`));
			});
		});
	} catch (error) {
		child.kill('SIGTERM');
		await rm(userDataDir, { recursive: true, force: true, maxRetries: 3 });
		throw error;
	}
	return {
		wsUrl,
		async close() {
			if (child.exitCode === null) {
				child.kill('SIGTERM');
				await new Promise((resolve) => {
					const timer = setTimeout(resolve, 5000);
					child.once('exit', () => {
						clearTimeout(timer);
						resolve();
					});
				});
			}
			await rm(userDataDir, { recursive: true, force: true, maxRetries: 3 });
		}
	};
}

export class CdpConnection {
	#nextId = 1;
	#pending = new Map();
	#handlers = new Set();
	#ws;

	constructor(url) {
		this.url = url;
	}

	async open() {
		this.#ws = new WebSocket(this.url);
		await new Promise((resolve, reject) => {
			this.#ws.addEventListener('open', resolve, { once: true });
			this.#ws.addEventListener('error', () => reject(new Error('CDP WebSocket connection failed.')), { once: true });
		});
		this.#ws.addEventListener('message', (event) => this.#dispatch(JSON.parse(String(event.data))));
		this.#ws.addEventListener('close', () => {
			for (const entry of this.#pending.values()) entry.reject(new Error('CDP connection closed.'));
			this.#pending.clear();
		});
		return this;
	}

	#dispatch(message) {
		if (message.id !== undefined) {
			const entry = this.#pending.get(message.id);
			if (!entry) return;
			this.#pending.delete(message.id);
			if (message.error) entry.reject(new Error(`${entry.method} failed: ${message.error.message}`));
			else entry.resolve(message.result ?? {});
			return;
		}
		for (const handler of this.#handlers) handler(message);
	}

	send(method, params = {}, sessionId) {
		const id = this.#nextId++;
		this.#ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
		return new Promise((resolve, reject) => this.#pending.set(id, { resolve, reject, method }));
	}

	on(handler) {
		this.#handlers.add(handler);
		return () => this.#handlers.delete(handler);
	}

	close() {
		this.#ws?.close();
	}
}

const pathOf = (raw) => {
	try {
		return new URL(raw).pathname;
	} catch {
		return null;
	}
};
export const pathWithQueryOf = (raw) => {
	try {
		const u = new URL(raw);
		return `${u.pathname}${u.search}`;
	} catch {
		return null;
	}
};
export const isApiUrl = (raw) => pathOf(raw)?.startsWith('/api/') ?? false;

export const isTelemetryUrl = (raw) => {
	const path = pathOf(raw);
	return (
		path === '/api/v1/activity/experience-events' ||
		path === '/api/v1/activity/experience-contract' ||
		path === '/api/v1/activity/experience-events/flush'
	);
};

/** One DevTools page target. Records every request so each navigation has its own API waterfall. */
export class MeasuredPage {
	#cdp;
	#sessionId;
	#requests = new Map();
	#apiInFlight = new Set();
	#lastApiEndAt = 0;
	#loadAt = null;
	#jsExceptions = 0;

	static async open(cdp) {
		const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
		const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
		const page = new MeasuredPage(cdp, sessionId);
		cdp.on((message) => {
			if (message.sessionId === sessionId) page.#onEvent(message);
		});
		for (const domain of ['Page', 'Network', 'Runtime']) await cdp.send(`${domain}.enable`, {}, sessionId);
		return page;
	}

	constructor(cdp, sessionId) {
		this.#cdp = cdp;
		this.#sessionId = sessionId;
	}

	#onEvent({ method, params }) {
		const now = performance.now();
		switch (method) {
			case 'Network.requestWillBeSent': {
				const { requestId, request, type, timestamp } = params;
				if (request.method === 'OPTIONS') return;
				const isApi = isApiUrl(request.url);
				const isTelemetry = isTelemetryUrl(request.url);
				this.#requests.set(requestId, {
					method: request.method,
					url: request.url,
					type,
					ts: timestamp,
					status: null,
					failed: null,
					responseTs: null,
					endTs: null,
					stream: false,
					telemetry: isTelemetry,
					serverDurMs: null,
					encodedBytes: null
				});
				// Background telemetry flushes must not keep page readiness in flight.
				if (isApi && !isTelemetry) this.#apiInFlight.add(requestId);
				return;
			}
			case 'Network.responseReceived': {
				const record = this.#requests.get(params.requestId);
				if (!record) return;
				record.status = params.response.status;
				record.responseTs = params.timestamp;
				const headers = params.response.headers || {};
				const serverTiming = headers['server-timing'] || headers['Server-Timing'] || '';
				const durMatch = /dur=([0-9.]+)/.exec(serverTiming);
				record.serverDurMs = durMatch ? round(Number(durMatch[1])) : null;
				if (params.response.mimeType === 'text/event-stream') {
					// A stream never finishes; it counts as settled once its headers arrive.
					record.stream = true;
					if (!record.telemetry) {
						this.#apiInFlight.delete(params.requestId);
						this.#lastApiEndAt = now;
					}
				}
				return;
			}
			case 'Network.loadingFinished': {
				const record = this.#requests.get(params.requestId);
				if (!record) return;
				record.endTs = params.timestamp;
				record.encodedBytes = params.encodedDataLength;
				if (!record.telemetry) {
					this.#apiInFlight.delete(params.requestId);
					this.#lastApiEndAt = now;
				}
				return;
			}
			case 'Network.loadingFailed': {
				const record = this.#requests.get(params.requestId);
				if (!record) return;
				record.failed = params.errorText || 'failed';
				record.endTs = params.timestamp;
				if (!record.telemetry) {
					this.#apiInFlight.delete(params.requestId);
					this.#lastApiEndAt = now;
				}
				return;
			}
			case 'Page.loadEventFired':
				this.#loadAt = now;
				return;
			case 'Runtime.exceptionThrown':
				this.#jsExceptions++;
				return;
			default:
		}
	}

	async #evaluate(expression) {
		const result = await this.#cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, this.#sessionId);
		if (result.exceptionDetails) throw new Error('page evaluation threw; details withheld to keep credentials out of logs.');
		return result.result.value;
	}

	async setCacheDisabled(disabled) {
		await this.#cdp.send('Network.setCacheDisabled', { cacheDisabled: disabled }, this.#sessionId);
	}

	async #waitUntil(predicate, timeoutMs, intervalMs = 100) {
		const deadline = performance.now() + timeoutMs;
		while (performance.now() < deadline) {
			if (await predicate()) return true;
			await delay(intervalMs);
		}
		return false;
	}

	/** Load `url` and wait for it to settle. Never throws for page behaviour; only for broken CDP. */
	async navigate(url, { timeoutMs = 30000, quietMs = 500 } = {}) {
		this.#requests.clear();
		this.#apiInFlight.clear();
		this.#lastApiEndAt = 0;
		this.#loadAt = null;
		this.#jsExceptions = 0;
		const startedAt = performance.now();
		const nav = await this.#cdp.send('Page.navigate', { url }, this.#sessionId);
		if (nav.errorText) return this.#result({ url, startedAt, status: 'error', error: nav.errorText, ready: false });

		let settledAt = null;
		const ready = await this.#waitUntil(() => {
			if (this.#loadAt === null || this.#apiInFlight.size > 0) return false;
			const settled = Math.max(this.#loadAt, this.#lastApiEndAt);
			if (performance.now() - settled < quietMs) return false;
			settledAt = settled;
			return true;
		}, timeoutMs);

		let snapshot = {};
		try {
			snapshot = (await this.#evaluate(`(() => {
				const nav = performance.getEntriesByType('navigation')[0];
				const hrefs = Array.from(document.querySelectorAll('a[href]'), (a) => {
					try {
						const u = new URL(a.href, location.origin);
						return u.origin === location.origin ? u.pathname : null;
					} catch {
						return null;
					}
				}).filter(Boolean);
				return {
					href: location.href,
					responseStartMs: nav ? nav.responseStart : null,
					domContentLoadedMs: nav ? nav.domContentLoadedEventEnd : null,
					bodyChars: (document.body ? document.body.innerText : '').trim().length,
					busyIndicators: document.querySelectorAll('[aria-busy="true"]').length,
					links: Array.from(new Set(hrefs))
				};
			})()`)) ?? {};
		} catch {
			snapshot = {};
		}
		return this.#result({ url, startedAt, settledAt, ready, snapshot, status: null });
	}

	#result({ url, startedAt, settledAt = null, ready, snapshot = {}, status, error = null }) {
		const finalPath = snapshot.href ? pathOf(snapshot.href) : null;
		const requestedPath = pathOf(url);
		const allApi = [...this.#requests.values()].filter((r) => isApiUrl(r.url));
		const formatCall = (r) => {
			const ttfb = r.responseTs !== null ? round((r.responseTs - r.ts) * 1000) : null;
			const rawTotal = r.endTs !== null && !r.failed ? round((r.endTs - r.ts) * 1000) : null;
			const download = r.endTs !== null && r.responseTs !== null && !r.failed ? round(Math.max(0, (r.endTs - r.responseTs) * 1000)) : null;
			return {
				endpoint: endpointKey(r.method, r.url),
				method: r.method,
				path: pathWithQueryOf(r.url),
				status: r.failed ? 'failed' : r.status,
				error: r.failed,
				ttfb_ms: ttfb,
				download_ms: download,
				// Clamp total to at least TTFB to prevent sub-millisecond CDP event timestamp inversion from producing total < TTFB
				total_ms: rawTotal !== null && ttfb !== null ? Math.max(rawTotal, ttfb) : rawTotal,
				server_dur_ms: r.serverDurMs,
				stream: r.stream,
				telemetry: r.telemetry,
				pending: r.endTs === null && !r.stream,
				encoded_bytes: r.encodedBytes
			};
		};
		const api = allApi.filter((r) => !r.telemetry).map(formatCall);
		const telemetry = allApi.filter((r) => r.telemetry).map(formatCall);
		let finalStatus = status;
		if (!finalStatus) {
			if (!ready) finalStatus = 'not_ready';
			else if (finalPath !== requestedPath) finalStatus = 'redirected';
			else if (snapshot.bodyChars === 0) finalStatus = 'blank';
			else finalStatus = 'ok';
		}
		return {
			requested: redactUrl(url),
			final: snapshot.href ? redactUrl(snapshot.href) : null,
			final_path: finalPath,
			status: finalStatus,
			error,
			ready,
			ready_ms: ready && settledAt !== null ? round(settledAt - startedAt) : null,
			load_ms: this.#loadAt !== null ? round(this.#loadAt - startedAt) : null,
			document_ttfb_ms: round(snapshot.responseStartMs),
			dom_content_loaded_ms: round(snapshot.domContentLoadedMs),
			body_chars: snapshot.bodyChars ?? null,
			busy_indicators: snapshot.busyIndicators ?? null,
			links: snapshot.links ?? [],
			js_exceptions: this.#jsExceptions,
			api_pending_at_end: this.#apiInFlight.size,
			api,
			telemetry
		};
	}

	/** Read the auth token and project ID the app stored for this tab. */
	async sessionAuth() {
		const raw = await this.#evaluate(`sessionStorage.getItem('afterglow_auth')`);
		if (!raw) return { token: null, projectId: null };
		try {
			const parsed = JSON.parse(raw);
			return {
				token: parsed.token ?? null,
				projectId: parsed.projectId ?? parsed.project_id ?? null
			};
		} catch {
			return { token: null, projectId: null };
		}
	}

	async sessionToken() {
		return (await this.sessionAuth()).token;
	}

	/** Wait for the user to complete login in the opened browser window. */
	async waitForInteractiveLogin({ origin, timeoutMs = 300000, onProgress = () => {} }) {
		await this.navigate(`${origin}/login`, { timeoutMs: 30000, quietMs: 200 });
		onProgress({ message: 'Browser opened at /login. Waiting for you to sign in in the Chrome window...' });
		const startedAt = performance.now();
		const signedIn = await this.#waitUntil(
			async () => {
				const check = await this.#evaluate(`(() => {
					const raw = sessionStorage.getItem('afterglow_auth');
					return Boolean(raw && location.pathname !== '/login');
				})()`);
				return check === true;
			},
			timeoutMs,
			500
		);
		check(signedIn, 'Interactive login timed out (5 minutes).');
		const loginMs = round(performance.now() - startedAt);
		onProgress({ message: `Interactive login detected! Completed in ${loginMs} ms.` });
		return { login_ms: loginMs, status: 200, interactive: true };
	}

	/** Sign in through the real login form. The login POST timing is the auth cost of the page visit. */
	async signIn({ origin, username, password, timeoutMs = 30000 }) {
		await this.navigate(`${origin}/login`, { timeoutMs, quietMs: 300 });
		const formReady = await this.#waitUntil(async () => (await this.#evaluate(`Boolean(document.getElementById('login-username') && document.getElementById('login-password'))`)) === true, timeoutMs);
		check(formReady, 'login form did not render; check the target URL.');
		await this.#evaluate(`(() => {
			const setValue = (id, value) => {
				const el = document.getElementById(id);
				Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value);
				el.dispatchEvent(new Event('input', { bubbles: true }));
			};
			setValue('login-username', ${JSON.stringify(username)});
			setValue('login-password', ${JSON.stringify(password)});
			document.querySelector('form.login-form').requestSubmit();
			return true;
		})()`);
		const signedIn = await this.#waitUntil(async () => (await this.#evaluate(`Boolean(sessionStorage.getItem('afterglow_auth')) && location.pathname !== '/login'`)) === true, timeoutMs, 200);
		const loginPost = [...this.#requests.values()].find((r) => r.method === 'POST' && pathOf(r.url) === '/api/v1/auth/login');
		check(signedIn, 'sign-in did not complete; check AFTERGLOW_LATENCY_USERNAME and AFTERGLOW_LATENCY_PASSWORD.');
		check(loginPost && loginPost.endTs !== null, 'sign-in completed without a measurable login request.');
		return { login_ms: round((loginPost.endTs - loginPost.ts) * 1000), status: loginPost.status };
	}
}

/**
 * Visit every route `passes` times in one tab after signing in. Pass 1 disables the HTTP cache
 * (cold load); later passes keep it (warm load). Sign-in timing is returned separately.
 */
export async function runBrowserLane({
	origin,
	username,
	password,
	routes,
	pendingDynamicRoutes = [],
	passes = 2,
	quietMs = 500,
	readyTimeoutMs = 30000,
	headless = true,
	interactiveLogin = false,
	executable,
	onProgress = () => {}
}) {
	const browser = await launchChrome(executable, { headless });
	const cdp = new CdpConnection(browser.wsUrl);
	let page;
	try {
		await cdp.open();
		page = await MeasuredPage.open(cdp);
		let login;
		if (interactiveLogin || (!username && !password)) {
			login = await page.waitForInteractiveLogin({ origin, timeoutMs: 300000, onProgress });
		} else {
			login = await page.signIn({ origin, username, password, timeoutMs: readyTimeoutMs });
		}
		const initialAuth = (await page.sessionAuth()) ?? {};
		return { ...await (async () => {
			const visits = [];
			const activeRoutes = [...routes];
			const allHarvestedLinks = new Set();
			let discoveredDynamic = [];

			for (let pass = 1; pass <= passes; pass++) {
				await page.setCacheDisabled(pass === 1);
				for (const route of activeRoutes) {
					const visit = await page.navigate(`${origin}${route.path}`, { timeoutMs: readyTimeoutMs, quietMs });
					visits.push({ pass, pattern: route.pattern, cache: pass === 1 ? 'cold' : 'warm', ...visit });
					for (const link of visit.links) allHarvestedLinks.add(link);
					onProgress({ pass, pattern: route.pattern, status: visit.status, ready_ms: visit.ready_ms });
				}
				// After cold pass 1, if there are pending dynamic routes without fixtures, attempt on-page link discovery
				if (pass === 1 && pendingDynamicRoutes.length > 0 && discoveredDynamic.length === 0) {
					const harvested = harvestDynamicRoutes(
						{ total: activeRoutes.length + pendingDynamicRoutes.length, measured: activeRoutes, skipped: pendingDynamicRoutes },
						allHarvestedLinks
					);
					if (harvested.newlyMeasured.length > 0) {
						discoveredDynamic = harvested.newlyMeasured;
						activeRoutes.push(...discoveredDynamic);
						for (const route of discoveredDynamic) {
							const visit = await page.navigate(`${origin}${route.path}`, { timeoutMs: readyTimeoutMs, quietMs });
							visits.push({ pass: 1, pattern: route.pattern, cache: 'cold', ...visit });
							for (const link of visit.links) allHarvestedLinks.add(link);
							onProgress({ pass: 1, pattern: route.pattern, status: visit.status, ready_ms: visit.ready_ms });
						}
					}
				}
			}
			const finalAuth = (await page.sessionAuth()) ?? {};
			const token = finalAuth.token || initialAuth.token;
			const projectId = finalAuth.projectId || initialAuth.projectId;
			return { login, visits, token, projectId, discoveredDynamic, allHarvestedLinks: Array.from(allHarvestedLinks) };
		})() };
	} finally {
		cdp.close();
		await browser.close();
	}
}
