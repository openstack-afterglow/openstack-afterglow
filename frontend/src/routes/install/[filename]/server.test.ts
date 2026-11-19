import { afterEach, describe, expect, it, vi } from 'vitest';
import { GET, HEAD } from './+server';

const requestEvent = (filename: string, init?: RequestInit) => ({
	params: { filename },
	request: new Request(`https://dashboard.example/install/${filename}?url=https://ignored.example`, init),
}) as Parameters<typeof GET>[0];

afterEach(() => {
	vi.unstubAllEnvs();
	vi.unstubAllGlobals();
});

describe('public Lumen downloads', () => {
	it.each(['lumen.sh', 'lumen.ps1'])('forwards only the fixed installer path and cache validator for %s', async (filename) => {
		vi.stubEnv('BACKEND_INTERNAL_ORIGIN', 'http://backend.test:8000');
		const fetch = vi.fn().mockResolvedValue(new Response('rendered script', { headers: {
			'content-type': 'text/plain; charset=utf-8', etag: '"current"', 'Set-Cookie': 'internal-data',
		} }));
		vi.stubGlobal('fetch', fetch);
		const response = await GET(requestEvent(filename, { headers: {
			'if-none-match': '"old"', cookie: 'local-session', authorization: 'Bearer ignored', host: 'ignored.example',
		} }));
		const [[url, options]] = fetch.mock.calls;
		expect(url.href).toBe(`http://backend.test:8000/api/v1/install/${filename}`);
		expect(options.redirect).toBe('error');
		expect([...options.headers]).toEqual([['if-none-match', '"old"']]);
		expect(response.status).toBe(200);
		expect(await response.text()).toBe('rendered script');
		expect(response.headers.get('content-type')).toBe('text/plain; charset=utf-8');
		expect(response.headers.get('cache-control')).toBe('no-cache');
		expect(response.headers.get('etag')).toBe('"current"');
		expect(response.headers.has('set-cookie')).toBe(false);
	});

	it('preserves a conditional HEAD response without downloading or inventing a body', async () => {
		const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 304, headers: { etag: '"current"' } }));
		vi.stubGlobal('fetch', fetch);
		const response = await HEAD(requestEvent('lumen.sh', { method: 'HEAD', headers: { 'if-none-match': '"current"' } }));
		expect(fetch.mock.calls[0][1].method).toBe('HEAD');
		expect(response.status).toBe(304);
		expect(response.body).toBeNull();
		expect(response.headers.get('etag')).toBe('"current"');
	});

	it('does not fetch a template or proxy an unexpected upstream page', async () => {
		const fetch = vi.fn().mockResolvedValue(new Response('<html>not a script</html>', { headers: { 'content-type': 'text/html' } }));
		vi.stubGlobal('fetch', fetch);
		await expect(GET(requestEvent('lumen.sh.template'))).rejects.toMatchObject({ status: 404 });
		expect(fetch).not.toHaveBeenCalled();
		await expect(GET(requestEvent('lumen.sh'))).rejects.toMatchObject({ status: 502 });
	});
});
