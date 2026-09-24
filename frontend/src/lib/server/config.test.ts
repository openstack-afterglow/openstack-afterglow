// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';

import { deriveBrowserApiBase } from './config';

afterEach(() => {
	vi.resetModules();
	vi.doUnmock('fs');
	vi.unstubAllEnvs();
});

describe('deriveBrowserApiBase', () => {
	it('prefers explicit public_api_base over frontend_base_url', () => {
		expect(
			deriveBrowserApiBase(
				{
					public_api_base: 'https://api.example.com/root/path',
					frontend_base_url: 'https://frontend.example.com/app',
					backend_port: 9000,
				},
				{},
			),
		).toBe('https://api.example.com');
	});

	it('lets PUBLIC_API_BASE override afterglow.conf for docker compose', () => {
		expect(
			deriveBrowserApiBase(
				{
					public_api_base: 'https://cloud.dmslab.re.kr',
					frontend_base_url: 'https://cloud.dmslab.re.kr',
					backend_port: 8000,
				},
				{ PUBLIC_API_BASE: 'http://localhost:8000' },
			),
		).toBe('http://localhost:8000');
	});

	it('falls back to frontend_base_url when public_api_base is empty or invalid', () => {
		expect(
			deriveBrowserApiBase(
				{
					public_api_base: 'not a url',
					frontend_base_url: 'https://afterglow.example.com/app',
					backend_port: 9000,
				},
				{},
			),
		).toBe('https://afterglow.example.com');
	});

	it('uses backend_port for local development when no public origin is configured', () => {
		expect(deriveBrowserApiBase({ backend_port: 8123 }, {})).toBe('http://localhost:8123');
	});
});

describe('loadPublicSiteConfig fallback', () => {
	it('uses PUBLIC_API_BASE when the frontend config mount is unavailable', async () => {
		vi.stubEnv('PUBLIC_API_BASE', 'https://cloud.dmslab.re.kr');
		vi.doMock('fs', async (importOriginal) => ({
			...(await importOriginal()),
			readFileSync: vi.fn(() => {
				throw new Error('ENOENT');
			}),
		}));

		// The module must be loaded after the filesystem mock to exercise its no-config boundary.
		const { loadPublicSiteConfig } = await import('./config');

		expect(loadPublicSiteConfig().runtime.api_base).toBe('https://cloud.dmslab.re.kr');
	});

});

describe('frontend CSP branding origins', () => {
	afterEach(() => {
		vi.resetModules();
		vi.doUnmock('$lib/server/config');
	});

	it('allows configured runtime and uploaded branding origins in CSP directives', async () => {
		const apiOrigin = 'https://api.example.com';
		const s3Origin = 'https://s3.example.com';
		const githubOrigin = 'https://api.github.com';

		vi.resetModules();
		vi.doMock('$lib/server/config', () => ({
			loadPublicSiteConfig: () => ({
				site_name: 'Afterglow',
				site_description: 'OpenStack VM + OverlayFS 배포 플랫폼',
				logo_path: 'https://uploads.example.com/legacy.png',
				logo_dark_path: '/api/v1/site-config/assets/logo_dark',
				logo_light_path: 'https://cdn.example.com/login-light.png',
				favicon_path: '/favicon.ico',
				refresh_interval_ms: 5000,
				services: { magnum: false, manila: false, zun: false, k3s: false, trove: false, swift: false, barbican: false },
				runtime: {
					api_base: apiOrigin,
					s3_base: s3Origin,
					grafana_base: '',
					librechat_base: '',
					gitlab_base: '',
				},
			}),
		}));

		// Test-only dynamic import: hooks.server must be loaded after vi.doMock so the mocked config module is bound.
		const { handle } = await import('../../hooks.server');
		const response = await handle({
			event: {
				url: new URL('https://frontend.example.com/'),
				locals: {},
				cookies: { get: vi.fn() },
			} as never,
			resolve: vi.fn(async () => new Response('ok', { headers: new Headers() })),
		});

		const csp = response.headers.get('Content-Security-Policy');
		expect(csp).toBeTruthy();
		const directives = new Map<string, string[]>();
		for (const directive of csp!.split(';')) {
			const [name, ...sources] = directive.trim().split(/\s+/);
			if (name) directives.set(name, sources);
		}

		expect([...directives.keys()]).toEqual(
			expect.arrayContaining(['default-src', 'script-src', 'style-src', 'img-src', 'connect-src', 'font-src', 'frame-src', 'frame-ancestors']),
		);
		expect(directives.get('connect-src')).toEqual(expect.arrayContaining([apiOrigin, s3Origin]));
		expect(directives.get('connect-src')).not.toContain(githubOrigin);
		expect([...directives.values()].flat()).not.toContain(githubOrigin);
		expect(directives.get('img-src')).toEqual(
			expect.arrayContaining(["'self'", 'data:', 'blob:', 'https://api.example.com', 'https://uploads.example.com', 'https://cdn.example.com']),
		);
		expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff');
	});

	it('includes librechat_base and gitlab_base in frame-src (LibreChat embed + its own OIDC redirect)', async () => {
		const librechatOrigin = 'https://chat.dmslab.re.kr';
		const gitlabOrigin = 'https://git.dmslab.re.kr';

		vi.resetModules();
		vi.doMock('$lib/server/config', () => ({
			loadPublicSiteConfig: () => ({
				site_name: 'Afterglow',
				site_description: 'OpenStack VM + OverlayFS 배포 플랫폼',
				logo_path: '/logo.png',
				logo_dark_path: '/logo-white.png',
				logo_light_path: '/logo-dark.png',
				favicon_path: '/favicon.ico',
				refresh_interval_ms: 5000,
				services: { magnum: false, manila: false, zun: false, k3s: false, trove: false, swift: false, barbican: false },
				runtime: {
					api_base: 'https://api.example.com',
					s3_base: '',
					grafana_base: '',
					librechat_base: librechatOrigin,
					gitlab_base: gitlabOrigin,
				},
			}),
		}));

		const { handle } = await import('../../hooks.server');
		const response = await handle({
			event: {
				url: new URL('https://cloud.dmslab.re.kr/'),
				locals: {},
				cookies: { get: vi.fn() },
			} as never,
			resolve: vi.fn(async () => new Response('ok', { headers: new Headers() })),
		});

		const csp = response.headers.get('Content-Security-Policy');
		const frameSrcDirective = csp!.split(';').map((d) => d.trim()).find((d) => d.startsWith('frame-src'));

		expect(frameSrcDirective).toContain(librechatOrigin);
		expect(frameSrcDirective).toContain(gitlabOrigin);
	});
});
