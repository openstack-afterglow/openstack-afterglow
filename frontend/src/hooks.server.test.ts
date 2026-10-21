// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Handle } from '@sveltejs/kit';

import type { PublicSiteConfig } from '$lib/types/siteConfig';
import { LOCALES, LOCALE_COOKIE } from '$lib/i18n/locales';

const baseConfig: PublicSiteConfig = {
	site_name: 'Afterglow',
	site_description: 'OpenStack VM + OverlayFS 배포 플랫폼',
	logo_path: '/afterglow-logo.svg',
	logo_dark_path: '/afterglow-logo.svg',
	logo_light_path: '/afterglow-logo.svg',
	favicon_path: '/favicon.svg',
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
	},
};

type CookieJar = Record<string, string | undefined>;

interface LanguageRequest {
	event: Parameters<Handle>[0]['event'];
}

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
		request: new Request(url),
		getClientAddress: vi.fn(() => '192.0.2.10'),
		locals: {},
		cookies,
		route: { id: routeId },
	} as unknown as Parameters<Handle>[0]['event'];
	const resolve = vi.fn(async () => new Response('ok', { status: 200, headers: new Headers() }));
	return { cookies, event, resolve, jar };
}

async function loadHandle(reporting = false) {
	vi.resetModules();
	vi.stubEnv('TRAFFIC_ANALYTICS_INGEST_URL', reporting ? 'http://backend:8000/api/v1/monitoring/traffic/events' : '');
	vi.stubEnv('TRAFFIC_ANALYTICS_INGEST_KEY', reporting ? 'k'.repeat(32) : '');
	vi.stubEnv('TRAFFIC_ANALYTICS_PEER_IS_SOCKET', 'false');
	vi.doMock('$lib/server/config', () => ({
		loadPublicSiteConfig: () => baseConfig,
	}));
	// Dynamic import required: hooks.server reads the mocked config module during module evaluation.
	return import('./hooks.server');
}

afterEach(() => {
	vi.resetModules();
	vi.doUnmock('$lib/server/config');
	vi.unstubAllEnvs();
	vi.unstubAllGlobals();
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

	it('lets audio players load browser-created object URLs without remote media origins', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/login');

		const response = await handle({ event: request.event, resolve: request.resolve });

		const directives = (response.headers.get('Content-Security-Policy') ?? '').split(';').map((part) => part.trim());
		expect(directives).toContain("media-src 'self' blob:");
	});

	it('allows only the fixed Gravatar image origin without expanding API connection authority', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/login');
		const response = await handle({ event: request.event, resolve: request.resolve });
		const directives = (response.headers.get('Content-Security-Policy') ?? '').split(';').map(part => part.trim());
		const images = directives.find(part => part.startsWith('img-src '))!;
		expect(images.split(' ')).toContain('https://www.gravatar.com');
		expect(images).not.toContain('https: ');
		expect(directives.find(part => part.startsWith('connect-src '))).not.toContain('gravatar');
	});
});

describe('authenticated project-independent domain surfaces', () => {
	it.each(['/select-domain', '/dashboard/iam'])('keeps %s authenticated without requiring a project cookie', async (path) => {
		const { handle } = await loadHandle();
		const anonymous = createRequest(`http://frontend.example.com${path}`, {}, path);
		const denied = await handle({ event: anonymous.event, resolve: anonymous.resolve });
		expect(denied.status).toBe(302);
		expect(denied.headers.get('Location')).toBe('/login');
		expect(anonymous.resolve).not.toHaveBeenCalled();
		const signedIn = createRequest(`http://frontend.example.com${path}`, { afterglow_session: 'active-session' }, path);
		const allowed = await handle({ event: signedIn.event, resolve: signedIn.resolve });
		expect(allowed.status).toBe(200);
		expect(allowed.headers.get('Location')).toBeNull();
		expect(signedIn.resolve).toHaveBeenCalledOnce();
	});
});

describe('public service documentation', () => {
	it.each(['/docs', '/docs/nova', '/docs/lumen?tutorial=on', '/docs/waygate?tutorial=admin'])(
		'serves %s without a session or tutorial redirect', async (path) => {
			const { handle } = await loadHandle();
			const request = createRequest(`http://frontend.example.com${path}`);
			const response = await handle({ event: request.event, resolve: request.resolve });
			expect(response.status).toBe(200);
			expect(response.headers.get('Location')).toBeNull();
			expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff');
		},
	);

	it.each(['/docsevil', '/docs-admin'])('does not exempt near-prefix %s from authentication', async (path) => {
		const { handle } = await loadHandle();
		const request = createRequest(`http://frontend.example.com${path}`);
		const response = await handle({ event: request.event, resolve: request.resolve });
		expect(response.status).toBe(302);
		expect(response.headers.get('Location')).toBe('/login');
	});

	it.each([false, true])('preserves missing-document 404 with a session=%s', async (signedIn) => {
		const { handle } = await loadHandle();
		const { event } = createNavRequest('http://frontend.example.com/docs/unknown', {
			cookies: signedIn ? { afterglow_session: 'active-session' } : {},
		});
		const response = await handle({ event, resolve: async () => new Response('missing document', { status: 404 }) });
		expect(response.status).toBe(404);
	});
});

describe('shared browser language preference', () => {
	async function renderLanguage(handle: Handle, request: LanguageRequest) {
		return handle({ event: request.event, resolve: async (_event, options) => {
			const html = await options!.transformPageChunk!({ html: '<html lang="%afterglow.lang%"></html>', done: true });
			return new Response(html);
		} });
	}

	it.each(LOCALES)('renders docs, login and authenticated pages in the saved %s language', async (locale) => {
		const { handle } = await loadHandle();
		for (const path of ['/', '/docs', '/docs/nova', '/login', '/dashboard']) {
			const request = createRequest(`https://frontend.example.com${path}`, {
				[LOCALE_COOKIE]: locale, afterglow_session: 'active-session',
			});
			const response = await renderLanguage(handle, request);
			expect(await response.text()).toBe(`<html lang="${locale}"></html>`);
			expect(request.event.locals.locale).toBe(locale);
		}
	});

	it.each(LOCALES)('persists an explicit docs choice of %s for subsequent login and console requests', async (locale) => {
		const { handle } = await loadHandle();
		const docs = createRequest(`https://frontend.example.com/docs/nova?lang=${locale}`, { afterglow_locale: 'en' });
		expect(await (await renderLanguage(handle, docs)).text()).toBe(`<html lang="${locale}"></html>`);
		expect(docs.cookies.set).toHaveBeenCalledWith('afterglow_locale', locale, {
			path: '/', maxAge: 31536000, sameSite: 'lax', httpOnly: false, secure: true,
		});
		for (const path of ['/login', '/dashboard']) {
			const next = createRequest(`https://frontend.example.com${path}`, { ...docs.jar, afterglow_session: 'active-session' });
			expect(await (await renderLanguage(handle, next)).text()).toBe(`<html lang="${locale}"></html>`);
		}
	});

	it.each([['ja', 'en'], ['nb', 'ms']] as const)('preloads docs language %s without changing saved %s choice', async (selected, saved) => {
		const { handle } = await loadHandle();
		const preload = createRequest(`https://frontend.example.com/docs/nova?lang=${selected}`, { [LOCALE_COOKIE]: saved });
		preload.event.isDataRequest = true;
		expect(await (await renderLanguage(handle, preload)).text()).toBe(`<html lang="${selected}"></html>`);
		expect(preload.cookies.set).not.toHaveBeenCalled();
		expect(preload.jar[LOCALE_COOKIE]).toBe(saved);
		const login = createRequest('https://frontend.example.com/login', preload.jar);
		expect(await (await renderLanguage(handle, login)).text()).toBe(`<html lang="${saved}"></html>`);
	});

	it.each([['en-US', 'ja'], ['untrusted', 'sw']] as const)('ignores unsupported docs language %s instead of discarding saved %s', async (unsupported, saved) => {
		const { handle } = await loadHandle();
		const request = createRequest(`https://frontend.example.com/docs?lang=${unsupported}`, { [LOCALE_COOKIE]: saved });
		expect(await (await renderLanguage(handle, request)).text()).toBe(`<html lang="${saved}"></html>`);
		expect(request.cookies.set).not.toHaveBeenCalled();
	});
});

describe('MCP OAuth consent shell', () => {
	it('serves an unauthenticated ticket handoff without caching or referrer leakage', async () => {
		const { handle } = await loadHandle();
		const { load } = await import('./routes/oauth/mcp/authorize/+page.server');
		const request = createRequest('http://frontend.example.com/oauth/mcp/authorize?ticket=' + 'a'.repeat(43));
		const response = await handle({ event: request.event, resolve: async () => {
			const headers = new Headers();
			load({ setHeaders: (values) => Object.entries(values).forEach(([name, value]) => headers.set(name, value)) });
			return new Response('consent shell', { headers });
		} });
		expect(response.status).toBe(200);
		expect(response.headers.get('Location')).toBeNull();
		expect(response.headers.get('Cache-Control')).toBe('no-store');
		expect(response.headers.get('Referrer-Policy')).toBe('no-referrer');
	});

	it('does not make adjacent OAuth routes public', async () => {
		const { handle } = await loadHandle();
		const request = createRequest('http://frontend.example.com/oauth/mcp/authorize-other');
		const response = await handle({ event: request.event, resolve: request.resolve });
		expect(response.status).toBe(302);
		expect(response.headers.get('Location')).toBe('/login');
	});

	it.each(['/auth/callback', '/signup', '/recover', '/recover/' + 'r'.repeat(43), '/invitations/' + 'a'.repeat(43), '/registrations/' + 'b'.repeat(43)])(
		'serves the token-bearing sign-in route %s without a session', async (path) => {
			const { handle } = await loadHandle();
			const request = createRequest(`http://frontend.example.com${path}`);
			const response = await handle({ event: request.event, resolve: request.resolve });
			expect(response.status).toBe(200);
			expect(response.headers.get('Location')).toBeNull();
			expect(response.headers.get('Referrer-Policy')).toBe('no-referrer');
		},
	);

	it.each(['/invitations/', '/registrations/', '/recover/', '/signup-other', '/recovery/token', '/auth/gitlab/callback', '/invitationsx/token'])(
		'keeps %s behind authentication', async (path) => {
			const { handle } = await loadHandle();
			const request = createRequest(`http://frontend.example.com${path}`);
			const response = await handle({ event: request.event, resolve: request.resolve });
			expect(response.status).toBe(302);
			expect(response.headers.get('Location')).toBe('/login');
		},
	);
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


describe('generated CSP preservation', () => {
	it.each(["'nonce-rendered-page'", "'sha256-rendered-page'"])(
		'keeps SvelteKit script authorization %s and runtime allowlists', async (source) => {
			const { handle } = await loadHandle();
			const request = createRequest('http://frontend.example.com/login');
			const response = await handle({ event: request.event, resolve: async () => new Response('html', {
				headers: { 'Content-Security-Policy': `script-src 'self' ${source}` },
			}) });
			const policy = response.headers.get('Content-Security-Policy')!;
			expect(policy).toContain(`script-src 'self' ${source}`);
			expect(policy).not.toContain("script-src 'self' 'unsafe-inline'");
			expect(policy).toContain("connect-src 'self' https://api.example.com wss://api.example.com");
		},
	);

	it('preserves the app shell policy rather than the original 404 nonce', async () => {
		const { handle } = await loadHandle();
		const { event, fetch } = createNavRequest('http://f.example.com/dashboard/missing', { cookies: SESSION });
		fetch.mockResolvedValueOnce(new Response('<script nonce="shell-nonce">SHELL</script>', {
			headers: { 'Content-Security-Policy': "script-src 'self' 'nonce-shell-nonce'" },
		}));
		const response = await handle({ event, resolve: async () => new Response('404', {
			status: 404, headers: { 'Content-Security-Policy': "script-src 'self' 'nonce-original-404'" },
		}) });
		expect(response.status).toBe(200);
		expect(response.headers.get('Content-Security-Policy')).toContain("'nonce-shell-nonce'");
		expect(response.headers.get('Content-Security-Policy')).not.toContain('original-404');
		expect(await response.text()).toContain('nonce="shell-nonce"');
	});
});

describe('traffic reporter hook integration', () => {
	it('observes early login redirects without changing authentication behavior or trusting forwarded addresses', async () => {
		const send = vi.fn<typeof fetch>(async () => new Response(null, { status: 202 }));
		vi.stubGlobal('fetch', send);
		const { handle } = await loadHandle(true);
		const { event, resolve } = createRequest('http://frontend.example.com/admin/instances/private?secret=value', {}, '/admin/instances/[id]');
		const response = await handle({ event, resolve });
		expect(response.status).toBe(302); expect(response.headers.get('location')).toBe('/login'); expect(resolve).not.toHaveBeenCalled();
		expect(event.getClientAddress).not.toHaveBeenCalled(); expect(send).toHaveBeenCalledTimes(1);
		const payload = JSON.parse(send.mock.calls[0][1]!.body as string);
		expect(payload).toMatchObject({ schema_version: 2, status: 302, route: '/admin', peer_ip: null, peer_verified: false, forwarded_for: null, request_bytes: null, response_bytes: 0, pageview: false });
		expect(JSON.stringify(payload)).not.toMatch(/private|secret|cookie/);
	});
	it('passes through rendered HTML bytes and generated CSP before nonblocking ingest', async () => {
		const send = vi.fn<typeof fetch>(async () => new Response(null, { status: 202 }));
		vi.stubGlobal('fetch', send);
		const { handle } = await loadHandle(true);
		const { event } = createRequest('http://frontend.example.com/login', {}, '/login');
		const response = await handle({ event, resolve: async () => new Response('한글', { headers: {
			'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': "script-src 'self' 'nonce-original'",
		} }) });
		expect(send).not.toHaveBeenCalled(); expect(response.headers.get('Content-Security-Policy')).toContain("'nonce-original'");
		expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff'); expect(await response.text()).toBe('한글');
		expect(JSON.parse(send.mock.calls[0][1]!.body as string)).toMatchObject({ route: '/login', status: 200, response_bytes: 6, pageview: true });
	});
});

describe('traffic reporter disabled', () => {
	it('passes the unchanged unauthenticated redirect and security headers without any transport', async () => {
		const send = vi.fn<typeof fetch>();
		vi.stubGlobal('fetch', send);
		const { handle } = await loadHandle(false);
		const unauthenticated = createRequest('http://frontend.example.com/dashboard');
		const redirected = await handle({ event: unauthenticated.event, resolve: unauthenticated.resolve });
		expect(redirected.status).toBe(302); expect(redirected.headers.get('location')).toBe('/login');
		const publicRequest = createRequest('http://frontend.example.com/login');
		const response = await handle({ event: publicRequest.event, resolve: publicRequest.resolve });
		expect(response.headers.get('X-Frame-Options')).toBe('DENY'); expect(await response.text()).toBe('ok');
		expect(send).not.toHaveBeenCalled(); expect(publicRequest.event.getClientAddress).not.toHaveBeenCalled();
	});
});
