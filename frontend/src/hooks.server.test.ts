// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Handle } from '@sveltejs/kit';

import type { PublicSiteConfig } from '$lib/types/siteConfig';

const baseConfig: PublicSiteConfig = {
	site_name: 'Afterglow',
	site_description: 'OpenStack VM + OverlayFS 배포 플랫폼',
	logo_path: '/logo.png',
	logo_dark_path: '/logo-white.png',
	logo_light_path: '/logo-dark.png',
	favicon_path: '/favicon.ico',
	refresh_interval_ms: 5000,
	services: {
		magnum: false,
		manila: false,
		zun: false,
		cloud_shell: false,
		k3s: false,
		trove: false,
		swift: false,
		barbican: false,
		waygate: false,
		chat: false,
		mcp: false,
	},
	runtime: {
		api_base: 'https://api.example.com',
		s3_base: '',
		grafana_base: '',
		librechat_base: '',
		gitlab_base: '',
	},
};

type CookieJar = Record<string, string | undefined>;

function createRequest(url: string, initialCookies: CookieJar = {}, routeId: string | null = '/[...path]') {
	const jar = { ...initialCookies };
	const cookies = {
		get: vi.fn((name: string) => jar[name]),
		set: vi.fn((name: string, value: string) => {
			jar[name] = value;
		}),
		delete: vi.fn((name: string) => {
			delete jar[name];
		}),
	};
	const event = {
		url: new URL(url),
		locals: {},
		cookies,
		route: { id: routeId },
	} as unknown as Parameters<Handle>[0]['event'];
	const resolve = vi.fn(async () => new Response('ok', { status: 200, headers: new Headers() }));
	return { cookies, event, resolve, jar };
}

async function loadHandle() {
	vi.resetModules();
	vi.doMock('$lib/server/config', () => ({
		loadPublicSiteConfig: () => baseConfig,
	}));
	// Dynamic import required: hooks.server reads the mocked config module during module evaluation.
	return import('./hooks.server');
}

afterEach(() => {
	vi.resetModules();
	vi.doUnmock('$lib/server/config');
});

describe('frontend health', () => {
	it('returns health JSON without a browser session', async () => {
		const { handle } = await loadHandle();
		const { GET } = await import('./routes/health/+server');
		const { event } = createRequest('http://frontend.example.com/health', {}, '/health');

		const response = await handle({ event, resolve: async () => GET() });

		expect(response.status).toBe(200);
		expect(await response.json()).toEqual({ status: 'ok' });
	});

	it('allows the API WebSocket origin used by terminal transports', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/login');

		const response = await handle({ event: request.event, resolve: request.resolve });

		expect(response.headers.get('Content-Security-Policy')).toContain(
			"connect-src 'self' https://api.example.com wss://api.example.com",
		);
	});
});

describe('hooks.server mockup gating', () => {
	it('redirects logged-out protected routes to /login when mockup mode is off', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/dashboard');

		const response = await handle({ event: request.event, resolve: request.resolve });

		expect(response.status).toBe(302);
		expect(response.headers.get('Location')).toBe('/login');
		expect(request.resolve).not.toHaveBeenCalled();
	});

	it('bootstraps tutorial mockup from the query without persisting a browser-wide cookie', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/dashboard?tutorial=on');

		const response = await handle({ event: request.event, resolve: request.resolve });

		expect(response.status).toBe(200);
		expect(request.resolve).toHaveBeenCalledOnce();
		expect(request.cookies.set).not.toHaveBeenCalled();
		expect(request.event.locals).toMatchObject({
			mockup: {
				active: true,
				profile: 'on',
				homePath: '/dashboard',
			},
		});
	});

	it('serves the tutorial volumes page without redirecting', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/dashboard/volumes?tutorial=on');

		const response = await handle({ event: request.event, resolve: request.resolve });

		expect(response.status).toBe(200);
		expect(request.resolve).toHaveBeenCalledOnce();
	});

	it('redirects unsupported tutorial paths to a query-bearing home route', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/admin?tutorial=on');

		const response = await handle({ event: request.event, resolve: request.resolve });

		expect(response.status).toBe(302);
		expect(response.headers.get('Location')).toBe('/dashboard?tutorial=on');
		expect(request.resolve).not.toHaveBeenCalled();
		expect(request.cookies.set).not.toHaveBeenCalled();
	});

	it('blocks an admin dynamic route even when its parameter looks like a static asset', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/dashboard/compute/instances/not-allowed.png?tutorial=admin');

		const response = await handle({ event: request.event, resolve: request.resolve });

		expect(response.status).toBe(302);
		expect(response.headers.get('Location')).toBe('/admin?tutorial=admin');
		expect(request.resolve).not.toHaveBeenCalled();
	});


	it.each([
		'/admin/instances',
		'/admin/volumes',
		'/admin/libraries',
		'/admin/topology',
		'/admin/containers',
		'/admin/secrets',
		'/admin/monitoring',
		'/admin/services',
		'/admin/users',
	])('serves administrator tutorial route %s without redirecting', async (path) => {
		const { handle } = await loadHandle();
		const request = createRequest(`http://frontend.example.com${path}?tutorial=admin`);

		const response = await handle({ event: request.event, resolve: request.resolve });

		expect(response.status).toBe(200);
		expect(request.resolve).toHaveBeenCalledOnce();
		expect(request.event.locals).toMatchObject({
			mockup: { active: true, profile: 'admin', homePath: '/admin' },
		});
	});

	it('redirects an administrator near-prefix route to the administrator home', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/admin/instances-near-prefix?tutorial=admin');

		const response = await handle({ event: request.event, resolve: request.resolve });

		expect(response.status).toBe(302);
		expect(response.headers.get('Location')).toBe('/admin?tutorial=admin');
		expect(request.resolve).not.toHaveBeenCalled();
	});
	it('keeps the profile allowlist active when a real session cookie is also present', async () => {
		const { handle } = await loadHandle();
		const request = createRequest(
			'http://frontend.example.com/admin?tutorial=on',
			{ afterglow_session: 'active-session' },
		);

		const response = await handle({ event: request.event, resolve: request.resolve });

		expect(response.status).toBe(302);
		expect(response.headers.get('Location')).toBe('/dashboard?tutorial=on');
		expect(request.resolve).not.toHaveBeenCalled();
	});
});

// 로그인 상태에서 문서 내비게이션이 404면 앱 셸(홈)을 200으로 내려 클라 라우터가 요청 경로를 렌더.
function createNavRequest(url: string, { accept = 'text/html', cookies = {} as CookieJar } = {}) {
	const jar = { ...cookies };
	const cookieApi = {
		get: vi.fn((name: string) => jar[name]),
		set: vi.fn((name: string, value: string) => {
			jar[name] = value;
		}),
		delete: vi.fn((name: string) => {
			delete jar[name];
		}),
	};
	const fetch = vi.fn(async (path: string) =>
		path === '/'
			? new Response('<html>APP SHELL</html>', { status: 200 })
			: new Response('x', { status: 404 }),
	);
	const event = {
		url: new URL(url),
		locals: {},
		cookies: cookieApi,
		route: { id: null },
		request: new Request(url, { headers: { accept } }),
		fetch,
	} as unknown as Parameters<Handle>[0]['event'];
	return { event, fetch };
}

const SESSION = { afterglow_session: 'active-session' };

describe('hooks.server SPA fallback', () => {
	it('serves the app shell (200) for a logged-in html navigation that 404s', async () => {
		const { handle } = await loadHandle();
		const { event, fetch } = createNavRequest('http://f.example.com/dashboard/deep', { cookies: SESSION });
		const resolve = vi.fn(async () => new Response('not found', { status: 404, headers: new Headers() }));

		const response = await handle({ event, resolve });

		expect(response.status).toBe(200);
		expect(await response.text()).toContain('APP SHELL');
		expect(fetch).toHaveBeenCalledWith('/');
	});

	it('keeps 404 for data requests (Accept: application/json)', async () => {
		const { handle } = await loadHandle();
		const { event, fetch } = createNavRequest('http://f.example.com/dashboard/deep', {
			accept: 'application/json',
			cookies: SESSION,
		});
		const resolve = vi.fn(async () => new Response('nf', { status: 404, headers: new Headers() }));

		const response = await handle({ event, resolve });

		expect(response.status).toBe(404);
		expect(fetch).not.toHaveBeenCalled();
	});

	it('keeps 404 for __data.json navigation', async () => {
		const { handle } = await loadHandle();
		const { event, fetch } = createNavRequest('http://f.example.com/dashboard/__data.json', { cookies: SESSION });
		const resolve = vi.fn(async () => new Response('nf', { status: 404, headers: new Headers() }));

		const response = await handle({ event, resolve });

		expect(response.status).toBe(404);
		expect(fetch).not.toHaveBeenCalled();
	});

	it('keeps 404 for backend-forwarded prefixes (/api, /v1, /.well-known)', async () => {
		const { handle } = await loadHandle();
		for (const path of ['/api/v1/x', '/v1/chat/completions', '/.well-known/oauth-protected-resource/api/v1/mcp']) {
			const { event, fetch } = createNavRequest(`http://f.example.com${path}`, { cookies: SESSION });
			const resolve = vi.fn(async () => new Response('nf', { status: 404, headers: new Headers() }));
			const response = await handle({ event, resolve });
			expect(response.status).toBe(404);
			expect(fetch).not.toHaveBeenCalled();
		}
	});

	it('does not fall back when the route resolves 200', async () => {
		const { handle } = await loadHandle();
		const { event, fetch } = createNavRequest('http://f.example.com/dashboard', { cookies: SESSION });
		const resolve = vi.fn(async () => new Response('ok', { status: 200, headers: new Headers() }));

		const response = await handle({ event, resolve });

		expect(response.status).toBe(200);
		expect(fetch).not.toHaveBeenCalled();
	});
});
