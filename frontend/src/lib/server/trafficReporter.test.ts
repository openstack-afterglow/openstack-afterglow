// @vitest-environment node
import { afterEach, describe, expect, it, vi, type Mock } from 'vitest';
import { error, redirect, type Handle, type RequestEvent } from '@sveltejs/kit';
import { createTrafficReporter, observeResponse, reporterConfig, trafficCategory, type TrafficEvent } from './trafficReporter';

const config = { url: 'http://backend:8000/api/v1/monitoring/traffic/events', key: 'k'.repeat(32), peerIsSocket: false };
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
function event(method = 'GET', route: string | null = '/admin/instances/[id]'): RequestEvent {
	return {
		route: { id: route }, request: new Request('https://example.test/admin/instances/private-id?token=secret', {
			method, headers: { cookie: 'session=secret', 'user-agent': 'secret-agent', 'x-forwarded-for': '1.2.3.4', 'cf-ipcountry': 'US' },
			...(method === 'POST' ? { body: 'private content' } : {}),
		}),
		getClientAddress: vi.fn(() => '192.0.2.10'),
		get cookies() { throw new Error('Reporter must not access cookies'); },
		fetch: vi.fn(() => { throw new Error('Reporter must use global transport, not event.fetch'); }),
	} as unknown as RequestEvent;
}
async function invoke(handle: Handle, response = new Response(null, { status: 204 }), requestEvent = event()) {
	return handle({ event: requestEvent, resolve: vi.fn(async () => response) });
}
function payload(send: Mock<typeof fetch>, index = 0): TrafficEvent {
	return JSON.parse(send.mock.calls[index][1]!.body as string);
}
afterEach(() => vi.useRealTimers());

describe('stream observation', () => {
	it('does not eagerly pull, clone, buffer or drain and forwards exact chunks and headers', async () => {
		const pull = vi.fn();
		const first = new Uint8Array([0, 255]); const second = new TextEncoder().encode('한');
		let index = 0;
		const input = new Response(new ReadableStream<Uint8Array>({ pull(controller) {
			pull(); if (index === 0) controller.enqueue(first); else if (index === 1) controller.enqueue(second); else controller.close(); index++;
		} }, { highWaterMark: 0 }), { status: 201, statusText: 'Created', headers: { 'content-type': 'text/html', 'x-security': 'preserved', 'set-cookie': 'existing=only' } });
		const clone = vi.spyOn(input, 'clone'); const finish = vi.fn();
		const output = observeResponse(input, finish);
		await settle(); expect(pull).not.toHaveBeenCalled(); expect(finish).not.toHaveBeenCalled();
		expect(output.status).toBe(201); expect(output.statusText).toBe('Created'); expect(output.headers.get('x-security')).toBe('preserved');
		expect(output.headers.get('set-cookie')).toBe('existing=only');
		const reader = output.body!.getReader();
		expect((await reader.read()).value).toBe(first); expect((await reader.read()).value).toBe(second);
		expect((await reader.read()).done).toBe(true); expect(finish).toHaveBeenCalledExactlyOnceWith(5); expect(clone).not.toHaveBeenCalled();
	});
	it('records unknown on cancellation and propagates the same reason without draining', async () => {
		const cancel = vi.fn(); const finish = vi.fn(); const reason = new Error('client disconnected');
		const output = observeResponse(new Response(new ReadableStream({ cancel }, { highWaterMark: 0 })), finish);
		await output.body!.cancel(reason); expect(cancel).toHaveBeenCalledExactlyOnceWith(reason); expect(finish).toHaveBeenCalledExactlyOnceWith(null);
	});
	it('records unknown after a partial read then cancellation', async () => {
		const cancel = vi.fn(); const finish = vi.fn();
		const output = observeResponse(new Response(new ReadableStream({ pull(controller) { controller.enqueue(new Uint8Array(4)); }, cancel }, { highWaterMark: 0 })), finish);
		const reader = output.body!.getReader(); await reader.read(); await reader.cancel('stop');
		expect(finish).toHaveBeenCalledExactlyOnceWith(null); expect(cancel).toHaveBeenCalledWith('stop');
	});
	it('keeps the original stream error and does not claim partial bytes as complete', async () => {
		const failure = new Error('stream failed'); const finish = vi.fn(); let pulled = false;
		const output = observeResponse(new Response(new ReadableStream({ pull(controller) {
			if (!pulled) { pulled = true; controller.enqueue(new Uint8Array(2)); } else controller.error(failure);
		} }, { highWaterMark: 0 })), finish);
		const reader = output.body!.getReader(); await reader.read(); await expect(reader.read()).rejects.toBe(failure);
		expect(finish).toHaveBeenCalledExactlyOnceWith(null);
	});
	it('cancels an outstanding read without double reporting or stream-controller errors', async () => {
		const finish = vi.fn(); const cancel = vi.fn();
		const output = observeResponse(new Response(new ReadableStream({ pull() {}, cancel }, { highWaterMark: 0 })), finish);
		const reader = output.body!.getReader(); const read = reader.read(); await settle(); await reader.cancel('stop');
		expect((await read).done).toBe(true); expect(finish).toHaveBeenCalledExactlyOnceWith(null); expect(cancel).toHaveBeenCalledExactlyOnceWith('stop');
	});
	it('returns zero for absent bodies and fails open when a callback throws or a body is locked', async () => {
		const finish = vi.fn(() => { throw new Error('report failure'); });
		const empty = new Response(null, { status: 204 }); expect(observeResponse(empty, finish)).toBe(empty);
		const locked = new Response('body'); const reader = locked.body!.getReader(); const unknown = vi.fn();
		expect(observeResponse(locked, unknown)).toBe(locked); expect(unknown).toHaveBeenCalledWith(null); reader.releaseLock();
		expect(await observeResponse(new Response('ok'), finish).text()).toBe('ok');
	});
	it('treats byte observations above the backend 1 TiB limit as unknown without huge allocation', async () => {
		const chunk = new Uint8Array(1); Object.defineProperty(chunk, 'byteLength', { value: 2 ** 40 + 1 });
		const finish = vi.fn();
		const output = observeResponse(new Response(new ReadableStream({ start(controller) { controller.enqueue(chunk); controller.close(); } })), finish);
		const reader = output.body!.getReader(); await reader.read(); await reader.read(); expect(finish).toHaveBeenCalledExactlyOnceWith(null);
	});
});

describe('server reporter transport and privacy', () => {
	it('is disabled without valid server-only configuration and defaults address trust off', async () => {
		expect(reporterConfig({})).toBeNull(); expect(reporterConfig({ TRAFFIC_ANALYTICS_INGEST_URL: config.url, TRAFFIC_ANALYTICS_INGEST_KEY: 'short' })).toBeNull();
		for (const url of ['file:///secret', '/api/events', 'https://user:password@backend/events', 'https://backend/events?secret=1']) expect(reporterConfig({ TRAFFIC_ANALYTICS_INGEST_URL: url, TRAFFIC_ANALYTICS_INGEST_KEY: config.key })).toBeNull();
		expect(reporterConfig({ TRAFFIC_ANALYTICS_INGEST_URL: config.url, TRAFFIC_ANALYTICS_INGEST_KEY: config.key })?.peerIsSocket).toBe(false);
        expect(reporterConfig({ TRAFFIC_ANALYTICS_INGEST_URL: config.url, TRAFFIC_ANALYTICS_INGEST_KEY: config.key, TRAFFIC_ANALYTICS_PEER_IS_SOCKET: 'true', ADDRESS_HEADER: 'x-forwarded-for' })?.peerIsSocket).toBe(false);
        expect(reporterConfig({ TRAFFIC_ANALYTICS_INGEST_URL: config.url, TRAFFIC_ANALYTICS_INGEST_KEY: config.key, TRAFFIC_ANALYTICS_PEER_IS_SOCKET: 'true' })?.peerIsSocket).toBe(true);
		const send = vi.fn<typeof fetch>(); const requestEvent = event(); const response = new Response('same');
		expect(await invoke(createTrafficReporter(null, { fetch: send }), response, requestEvent)).toBe(response); expect(send).not.toHaveBeenCalled(); expect(requestEvent.getClientAddress).not.toHaveBeenCalled();
	});
	it('sends only exact ingest fields, category and observed bytes; never consumes request data or trusts headers', async () => {
		const send = vi.fn<typeof fetch>(async () => new Response(null, { status: 202 })); const requestEvent = event('POST');
		const clone = vi.spyOn(requestEvent.request, 'clone');
		const response = await invoke(createTrafficReporter(config, { fetch: send }), new Response('ok'), requestEvent);
		expect(send).not.toHaveBeenCalled(); expect(await response.text()).toBe('ok'); await settle();
		const body = payload(send); expect(Object.keys(body).sort()).toEqual(['schema_version', 'id', 'at', 'status', 'route', 'peer_ip', 'peer_verified', 'forwarded_for', 'pageview', 'request_bytes', 'response_bytes', 'latency_ms', 'reporter_dropped_events'].sort());
		expect(body).toMatchObject({ schema_version: 2, route: '/admin', peer_ip: null, peer_verified: false, forwarded_for: '1.2.3.4', pageview: false, request_bytes: null, response_bytes: 2, reporter_dropped_events: 0 });
		expect(body.id).toMatch(/^[0-9a-f-]{36}$/); expect(Math.abs(body.at - Date.now() / 1000)).toBeLessThan(2); expect(body.latency_ms).toBeGreaterThanOrEqual(0);
		expect(JSON.stringify(body)).not.toMatch(/secret|private|user-agent|cookie|US/); expect(clone).not.toHaveBeenCalled(); expect(requestEvent.request.bodyUsed).toBe(false); expect(requestEvent.getClientAddress).not.toHaveBeenCalled(); expect(requestEvent.fetch).not.toHaveBeenCalled();
		expect(send.mock.calls[0][0]).toBe(config.url);
		expect(send.mock.calls[0][1]).toMatchObject({ credentials: 'omit', redirect: 'error', headers: { Authorization: `Bearer ${config.key}`, 'Content-Type': 'application/json' } });
	});
	it('uses only opted-in adapter address and reports unavailable adapter addresses as null', async () => {
		const send = vi.fn<typeof fetch>(async () => new Response(null, { status: 202 })); const handle = createTrafficReporter({ ...config, peerIsSocket: true }, { fetch: send });
		await invoke(handle); await settle(); expect(payload(send)).toMatchObject({ peer_ip: '192.0.2.10', peer_verified: true, forwarded_for: '1.2.3.4' });
		const requestEvent = event(); vi.mocked(requestEvent.getClientAddress).mockImplementation(() => { throw new Error('no adapter support'); });
		await invoke(handle, undefined, requestEvent); await settle(); expect(payload(send, 1).peer_ip).toBeNull();
	});
    it.each(['1'.repeat(1025), '"'.repeat(1024)])('bounds raw and escaped forwarded evidence without losing the observation', async (forwarded) => {
        const send = vi.fn<typeof fetch>(async () => new Response(null, { status: 202 }));
        const requestEvent = event(); requestEvent.request.headers.set('x-forwarded-for', forwarded);
        await invoke(createTrafficReporter({ ...config, peerIsSocket: true }, { fetch: send }), undefined, requestEvent);
        expect(payload(send).forwarded_for).toBe('invalid');
        expect(Buffer.byteLength(send.mock.calls[0][1]!.body as string, 'utf8')).toBeLessThanOrEqual(2048);
        expect(payload(send)).toMatchObject({ status: 204, response_bytes: 0, reporter_dropped_events: 0 });
    });
	it.each([
		['GET', 200, 'text/html; charset=utf-8', true], ['POST', 200, 'text/html', false],
		['GET', 302, 'text/html', false], ['GET', 500, 'text/html', false], ['GET', 200, 'application/json', false], ['HEAD', 200, 'text/html', false],
	] as const)('classifies server pageviews for %s %s %s', async (method, status, contentType, pageview) => {
		const send = vi.fn<typeof fetch>(async () => new Response(null, { status: 202 }));
		const response = await invoke(createTrafficReporter(config, { fetch: send }), new Response(null, { status, headers: { 'content-type': contentType } }), event(method));
		expect(response.status).toBe(status); expect(payload(send).pageview).toBe(pageview); await settle();
	});
	it('wraps early-return redirects/security headers and rethrows Kit redirects, HTTP errors and unexpected errors unchanged', async () => {
		const send = vi.fn<typeof fetch>(async () => new Response(null, { status: 202 }));
		const reporter = createTrafficReporter(config, { fetch: send });
		const security: Handle = async () => new Response(null, { status: 302, headers: { location: '/login', 'x-security': 'same' } });
		const handle: Handle = ({ event, resolve }) => reporter({ event, resolve: (inner) => security({ event: inner, resolve }) });
		const response = await invoke(handle); expect(response.headers.get('location')).toBe('/login'); expect(response.headers.get('x-security')).toBe('same'); expect(payload(send).status).toBe(302); await settle();
		for (const [throwError, status] of [[() => redirect(307, '/login'), 307], [() => error(403, 'denied'), 403], [() => { throw new Error('failure'); }, 500]] as const) {
			let original: unknown; try { throwError(); } catch (caught) { original = caught; }
			await expect(createTrafficReporter(config, { fetch: send })({ event: event(), resolve: async () => { throw original; } })).rejects.toBe(original);
			expect(payload(send, send.mock.calls.length - 1)).toMatchObject({ status, response_bytes: null, pageview: false }); await settle();
		}
	});
	it('bounds inflight delivery, does not block responses, and carries overflow plus failed delivery into the next report', async () => {
		const pending = Promise.withResolvers<Response>();
		const send = vi.fn<typeof fetch>()
			.mockImplementationOnce(() => pending.promise)
			.mockResolvedValue(new Response(null, { status: 202 }));
		const handle = createTrafficReporter(config, { fetch: send, maxInflight: 1 });
		expect((await invoke(handle)).status).toBe(204); await invoke(handle); expect(send).toHaveBeenCalledTimes(1);
		pending.reject(new Error('offline')); await settle(); await invoke(handle); expect(payload(send, 1).reporter_dropped_events).toBe(2); await settle();
	});
	it('fails open on HTTP failure and synchronous transport throws, then carries the loss', async () => {
		const send = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response('not available', { status: 503 })).mockImplementationOnce(() => { throw new Error('send failed'); }).mockResolvedValue(new Response(null, { status: 202 }));
		const handle = createTrafficReporter(config, { fetch: send });
		await invoke(handle); await settle(); await invoke(handle); await settle(); await invoke(handle);
		expect(payload(send, 2).reporter_dropped_events).toBe(2); await settle();
	});
	it('aborts on the deadline and frees the slot even when transport ignores cancellation', async () => {
		vi.useFakeTimers(); const send = vi.fn<typeof fetch>().mockImplementationOnce(() => Promise.withResolvers<Response>().promise).mockResolvedValue(new Response(null, { status: 202 }));
		const handle = createTrafficReporter(config, { fetch: send, maxInflight: 1, timeoutMs: 50 });
		await invoke(handle); await vi.advanceTimersByTimeAsync(50); expect(send.mock.calls[0][1]!.signal!.aborted).toBe(true);
		await invoke(handle); expect(payload(send, 1).reporter_dropped_events).toBe(1); await settle();
	});
	it('retains only fixed categories derived from route IDs, never actual dynamic URLs', () => {
		expect(trafficCategory('/(app)/dashboard/compute/[id]')).toBe('/dashboard'); expect(trafficCategory(null)).toBe('__unmatched__');
		expect(trafficCategory('/administer/[name]')).toBe('/other'); expect(trafficCategory('/')).toBe('/'); expect(trafficCategory('/(public)')).toBe('/');
		for (const route of ['/docs/[slug]', '/auth/gitlab/callback', '/login']) expect(trafficCategory(route)).toBe(route.split('/').slice(0, 2).join('/'));
	});
});
