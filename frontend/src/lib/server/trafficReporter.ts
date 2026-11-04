import { randomUUID } from 'node:crypto';
import { isHttpError, isRedirect, type Handle } from '@sveltejs/kit';

export interface TrafficEvent {
    schema_version: 2; id: string; at: number; status: number; route: string;
    peer_ip: string | null; peer_verified: boolean; forwarded_for: string | null;
	pageview: boolean; request_bytes: null; response_bytes: number | null;
	latency_ms: number; reporter_dropped_events: number;
	reporter_drop_reasons?: Partial<Record<DropReason, number>>;
}
type DropReason = 'timeout' | 'connection' | 'capacity' | 'rejected' | 'unknown';
const dropReasons: readonly DropReason[] = ['timeout', 'connection', 'capacity', 'rejected', 'unknown'];
const ingestPath = '/api/v1/monitoring/traffic/events';
const snapshotPath = '/api/v1/admin/monitoring/traffic';
const selfReportingPaths: Readonly<Record<string, true>> = {
	'/api/v1/activity/experience-events': true,
	'/api/v1/activity/experience-contract': true,
};
export interface ReporterConfig { url: string; key: string; peerIsSocket: boolean }
export function reporterConfig(env: Record<string, string | undefined>): ReporterConfig | null {
	const url = env.TRAFFIC_ANALYTICS_INGEST_URL;
	const key = env.TRAFFIC_ANALYTICS_INGEST_KEY;
	if (!url || !key || key.length < 32) return null;
	try {
		const parsed = new URL(url);
		if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash) return null;
	} catch { return null; }
    // ADDRESS_HEADER makes adapter getClientAddress header-derived, not a socket peer.
    return { url, key, peerIsSocket: env.TRAFFIC_ANALYTICS_PEER_IS_SOCKET === 'true' && !env.ADDRESS_HEADER };
}

// Never retain dynamic IDs, URLs, query strings or user-supplied paths.
export function trafficCategory(routeId: string | null): string {
	if (routeId === null) return '__unmatched__';
	const route = routeId.replace(/\/\([^/]+\)/g, '') || '/';
	if (route === '/') return '/';
    for (const category of ['/admin', '/dashboard', '/login', '/docs', '/auth', '/health']) {
		if (route === category || route.startsWith(`${category}/`)) return category;
	}
	return '/other';
}

// Pull only when the adapter consumes the response. No clone, tee, drain or buffering.
export function observeResponse(response: Response, finish: (bytes: number | null) => void): Response {
	let finished = false;
	const done = (bytes: number | null) => {
		if (finished) return;
		finished = true;
		try { finish(bytes); } catch { /* Reporting must not affect delivery. */ }
	};
	if (!response.body) { done(0); return response; }
	if (response.body.locked) { done(null); return response; }
	const reader = response.body.getReader();
	let bytes = 0;
	const body = new ReadableStream<Uint8Array>({
		async pull(controller) {
			try {
				const chunk = await reader.read();
				if (finished) return;
				if (chunk.done) { done(bytes <= 2 ** 40 ? bytes : null); reader.releaseLock(); controller.close(); }
				else { bytes = Math.min(2 ** 40 + 1, bytes + chunk.value.byteLength); controller.enqueue(chunk.value); }
			} catch (error) {
				if (finished) return;
				done(null);
				reader.releaseLock();
				controller.error(error);
			}
		},
		async cancel(reason) {
			done(null);
			try { await reader.cancel(reason); } finally { reader.releaseLock(); }
		},
	}, { highWaterMark: 0 });
	try { return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers }); }
	catch { reader.releaseLock(); done(null); return response; }
}

export function createTrafficReporter(
	config: ReporterConfig | null,
	{ fetch: send = globalThis.fetch, maxInflight = 16, timeoutMs = 2000 }:
	{ fetch?: typeof fetch; maxInflight?: number; timeoutMs?: number } = {},
): Handle {
	const ingestion = config ? new URL(config.url) : null;
	let inflight = 0;
	const dropped: Partial<Record<DropReason, number>> = {};
	const drop = (reason: DropReason, count = 1) => {
		dropped[reason] = Math.min(Number.MAX_SAFE_INTEGER, (dropped[reason] ?? 0) + count);
	};
	function report(event: Omit<TrafficEvent, 'reporter_dropped_events' | 'reporter_drop_reasons'>) {
		if (!config) return;
		if (inflight >= maxInflight) { drop('capacity'); return; }
		const carriedReasons: Partial<Record<DropReason, number>> = {};
		let carried = 0;
		for (const reason of dropReasons) {
			const count = Math.min(1_000_000 - carried, dropped[reason] ?? 0);
			if (count) { carriedReasons[reason] = count; dropped[reason]! -= count; carried += count; }
		}
		const payload: TrafficEvent = { ...event, reporter_dropped_events: carried,
			...(carried ? { reporter_drop_reasons: carriedReasons } : {}) };
		let body = JSON.stringify(payload);
		// JSON escaping must not turn invalid address evidence into a lost request.
		if (Buffer.byteLength(body, 'utf8') > 2048) {
			payload.forwarded_for = 'invalid';
			body = JSON.stringify(payload);
		}
		inflight++;
		// The deadline frees the bounded slot even if a custom transport ignores abort.
		void (async () => {
			const controller = new AbortController();
			let timer: NodeJS.Timeout | undefined;
			let failure: DropReason = 'unknown';
			try {
				// Runtime builds also support Node 20, which has no Promise.withResolvers.
				const deadline = new Promise<never>((_, reject) => {
					timer = setTimeout(() => { failure = 'timeout'; controller.abort(); reject(new Error('report deadline')); }, timeoutMs);
				});
				const delivery = (async () => {
					const result = await send(config.url, {
						method: 'POST', credentials: 'omit', redirect: 'error', signal: controller.signal,
						headers: { Authorization: `Bearer ${config.key}`, 'Content-Type': 'application/json' },
						body,
					});
					try { if (!result.ok) { failure = 'rejected'; throw new Error('report rejected'); } }
					finally { await result.body?.cancel(); }
				})();
				await Promise.race([delivery, deadline]);
			} catch (error) {
				// Fetch network failures are TypeError; do not inspect URLs/messages/causes.
				if (failure === 'unknown' && error instanceof TypeError) failure = 'connection';
				for (const reason of dropReasons) if (carriedReasons[reason]) drop(reason, carriedReasons[reason]);
				drop(failure);
			}
			finally { clearTimeout(timer); inflight--; }
		})();
	}
	return async ({ event, resolve }) => {
		if (!config) return resolve(event);
		const requestUrl = new URL(event.request.url);
		const path = requestUrl.pathname;
		// Never report ingestion itself, even when it fails: a proxy routed
		// through this hook must not recursively report its own POST.
		if (path === ingestPath || path === `${ingestPath}/` ||
			(ingestion && requestUrl.origin === ingestion.origin && path === ingestion.pathname)) return resolve(event);
		const diagnostic = Object.hasOwn(selfReportingPaths, path.endsWith('/') ? path.slice(0, -1) : path) ||
			((event.request.method === 'GET' || event.request.method === 'HEAD') &&
				(path === '/health' || path === snapshotPath || path === `${snapshotPath}/`));
		const start = performance.now();
		let address: string | null = null;
        if (config.peerIsSocket) {
            try { address = event.getClientAddress(); } catch { /* Adapter address unavailable. */ }
        }
        const forwarded = event.request.headers.get('x-forwarded-for');
        const base = {
            schema_version: 2, id: randomUUID(), route: trafficCategory(event.route.id),
            peer_ip: address && address.length <= 64 ? address : null,
            peer_verified: config.peerIsSocket,
            forwarded_for: forwarded && forwarded.length > 1024 ? 'invalid' : forwarded,
            request_bytes: null,
        } as const;
		const finish = (status: number, pageview: boolean, bytes: number | null) => {
			// Only a fully consumed successful diagnostic is noise. Cancelled or
			// failed streams remain observations with unknown byte coverage.
			if (diagnostic && status >= 200 && status < 300 && bytes !== null) return;
			report({
				...base, at: Date.now() / 1000, status, pageview, response_bytes: bytes,
				latency_ms: Math.max(0, performance.now() - start),
			});
		};
		try {
			const response = await resolve(event);
			const pageview = event.request.method === 'GET' && response.status >= 200 && response.status < 300 &&
				/^text\/html(?:;|$)/i.test(response.headers.get('content-type') ?? '');
			return observeResponse(response, (bytes) => finish(response.status, pageview, bytes));
		} catch (error) {
			finish(isRedirect(error) || isHttpError(error) ? error.status : 500, false, null);
			throw error;
		}
	};
}
