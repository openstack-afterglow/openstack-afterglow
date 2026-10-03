// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { resolveFaviconPath, resolveLandingLogoPath } from './brandAssets';

const branding = {
	logo_path: '/afterglow-logo.svg',
	logo_dark_path: '/afterglow-logo.svg',
	logo_light_path: '/afterglow-logo.svg',
	favicon_path: '/favicon.svg',
};

describe('theme-aware public brand assets', () => {
	it('preserves configured light and dark logo slots with shared-logo fallback', () => {
		expect(resolveLandingLogoPath({ ...branding, logo_light_path: '/api/logo-bright.png' }, 'dark')).toBe('/api/logo-bright.png');
		expect(resolveLandingLogoPath({ ...branding, logo_dark_path: '/api/logo-ink.png' }, 'light')).toBe('/api/logo-ink.png');
		expect(resolveLandingLogoPath({ ...branding, logo_light_path: '', logo_path: '/api/logo-shared.svg' }, 'dark')).toBe('/api/logo-shared.svg');
	});

	it('preserves a configured favicon', () => {
		expect(resolveFaviconPath({ favicon_path: '/api/custom-favicon.png' })).toBe('/api/custom-favicon.png');
	});
});
