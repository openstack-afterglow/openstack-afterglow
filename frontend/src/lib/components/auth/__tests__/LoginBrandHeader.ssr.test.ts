// @vitest-environment node

import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';
import { siteConfig } from '$lib/config/site';
import LoginBrandHeader from '../LoginBrandHeader.svelte';
import type { PublicSiteConfig } from '$lib/types/siteConfig';

type SvelteModule = typeof import('svelte');

const baseConfig: PublicSiteConfig = {
	site_name: 'Afterglow',
	site_description: 'OpenStack VM + OverlayFS 배포 플랫폼',
	logo_path: '/brand/fallback.png',
	logo_dark_path: '/brand/dark-slot.png',
	logo_light_path: '/brand/light-slot.png',
	favicon_path: '/favicon.svg',
	refresh_interval_ms: 5000,
	services: { magnum: false, manila: false, zun: false, cloud_shell: false, k3s: false, trove: false, swift: false, barbican: false, waygate: false, chat: false, mcp: false },
	runtime: {
		api_base: '',
		s3_base: '',
		grafana_base: '',
		librechat_base: '',
		gitlab_base: '',
	},
};

vi.mock('$app/environment', () => ({ browser: false, dev: false, building: false, version: 'test' }));
vi.mock('svelte', async () => {
	const actual = await vi.importActual<SvelteModule>('svelte');
	return { ...actual, onMount: vi.fn() };
});

describe('LoginBrandHeader SSR', () => {
	it('omits the login logo from SSR output until the client theme is mounted', async () => {
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
