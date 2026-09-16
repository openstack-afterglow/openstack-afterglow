import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import type { PublicSiteConfig } from '$lib/types/siteConfig';
import { siteConfig } from '$lib/config/site';
import { theme } from '$lib/stores/theme';
import type { ThemePreference } from '$lib/stores/theme';

import LoginBrandHeader from '../LoginBrandHeader.svelte';

const baseConfig: PublicSiteConfig = {
	site_name: 'Afterglow',
	site_description: 'OpenStack VM + OverlayFS 배포 플랫폼',
	logo_path: '/logo.png',
	logo_dark_path: '/logo-white.png',
	logo_light_path: '/logo-dark.png',
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

function buildConfig(overrides: Partial<PublicSiteConfig> = {}): PublicSiteConfig {
	return {
		...baseConfig,
		...overrides,
		services: { ...baseConfig.services, ...(overrides.services ?? {}) },
		runtime: { ...baseConfig.runtime, ...(overrides.runtime ?? {}) },
	};
}

describe('LoginBrandHeader', () => {
	beforeEach(() => {
		theme.set('system');
		siteConfig.set(buildConfig());
	});

	it.each<{
		name: string;
		preference: ThemePreference;
		config: Partial<PublicSiteConfig>;
		expectedSrc: string;
	}>([
		{
			name: 'resolved dark theme prefers the light-background-safe logo',
			preference: 'dark',
			config: { logo_light_path: '/brand/login-light.png' },
			expectedSrc: '/brand/login-light.png',
		},
		{
			name: 'resolved light theme prefers the dark-background-safe logo',
			preference: 'light',
			config: { logo_dark_path: '/brand/login-dark.png' },
			expectedSrc: '/brand/login-dark.png',
		},
		{
			name: 'dark theme falls back to legacy logo_path when logo_light_path is missing',
			preference: 'dark',
			config: { logo_path: '/brand/legacy.png', logo_light_path: '' },
			expectedSrc: '/brand/legacy.png',
		},
		{
			name: 'light theme falls back to legacy logo_path when logo_dark_path is missing',
			preference: 'light',
			config: { logo_path: '/brand/legacy.png', logo_dark_path: '' },
			expectedSrc: '/brand/legacy.png',
		},
	])('$name', async ({ preference, config, expectedSrc }) => {
		theme.set(preference);
		siteConfig.set(buildConfig(config));

		render(LoginBrandHeader);

		const img = await screen.findByRole('img', { name: 'Afterglow' });
		expect(img.getAttribute('src')).toBe(expectedSrc);
	});

	it('links back to the public homepage', () => {
		render(LoginBrandHeader);

		expect(screen.getByRole('link', { name: '메인 홈페이지로 돌아가기' }).getAttribute('href')).toBe('/');
	});
});
