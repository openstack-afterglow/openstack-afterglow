// @vitest-environment node

import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PublicSiteConfig } from '$lib/types/siteConfig';

type SvelteModule = typeof import('svelte');

const baseConfig: PublicSiteConfig = {
	site_name: 'Afterglow',
	site_description: 'OpenStack VM + OverlayFS 배포 플랫폼',
	logo_path: '/brand/fallback.png',
	logo_dark_path: '/brand/dark-slot.png',
	logo_light_path: '/brand/light-slot.png',
	favicon_path: '/favicon.ico',
	refresh_interval_ms: 5000,
	services: { magnum: false, manila: false, zun: false, k3s: false, trove: false, swift: false, barbican: false, waygate: false, chat: false, mcp: false },
	runtime: {
		api_base: '',
		s3_base: '',
		grafana_base: '',
		librechat_base: '',
		gitlab_base: '',
	},
};

afterEach(() => {
	vi.doUnmock('$app/environment');
	vi.doUnmock('svelte');
	vi.resetModules();
});

describe('LoginBrandHeader SSR', () => {
	it('omits the login logo from SSR output until the client theme is mounted', async () => {
		vi.resetModules();
		vi.doMock('$app/environment', () => ({ browser: false, dev: false, building: false, version: 'test' }));
		vi.doMock('svelte', async () => {
			const actual = await vi.importActual<SvelteModule>('svelte');
			return { ...actual, onMount: vi.fn() };
		});

		// Dynamic imports are required so the mocked $app/environment and no-op onMount apply before theme.ts and the component load.
		const { render } = await import('svelte/server');
		const { siteConfig } = await import('$lib/config/site');
		const { default: LoginBrandHeader } = await import('../LoginBrandHeader.svelte');

		siteConfig.set({
			...baseConfig,
			services: { ...baseConfig.services },
			runtime: { ...baseConfig.runtime },
		});

		const { body } = render(LoginBrandHeader);

		expect(body).not.toContain('/brand/light-slot.png');
		expect(body).not.toContain('/brand/dark-slot.png');
		expect(body).not.toContain('<img');
	});
});
