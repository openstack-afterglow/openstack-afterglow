// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { resolveFaviconPath, resolveLandingLogoPath } from './brandAssets';

const legacyBranding = {
	logo_path: '/logo.png',
	logo_dark_path: '/logo-white.png',
	logo_light_path: '/logo-dark.png',
	favicon_path: '/favicon.ico',
};

describe('theme-aware public brand assets', () => {
	it('uses icon-only defaults for legacy logo paths on matching surfaces', () => {
		expect(resolveLandingLogoPath(legacyBranding, 'dark')).toBe('/brand/afterglow-mark-light.svg');
		expect(resolveLandingLogoPath(legacyBranding, 'light')).toBe('/brand/afterglow-mark-dark.svg');
	});

	it('preserves configured light and dark logo slots with legacy fallback', () => {
		expect(resolveLandingLogoPath({ ...legacyBranding, logo_light_path: '/api/logo-bright.png' }, 'dark')).toBe('/api/logo-bright.png');
		expect(resolveLandingLogoPath({ ...legacyBranding, logo_dark_path: '/api/logo-ink.png' }, 'light')).toBe('/api/logo-ink.png');
		expect(resolveLandingLogoPath({ ...legacyBranding, logo_light_path: '', logo_path: '/api/logo-legacy.png' }, 'dark')).toBe('/api/logo-legacy.png');
	});

	it('restores the legacy /favicon.ico for the default config and preserves a configured favicon', () => {
		expect(resolveFaviconPath(legacyBranding, 'dark')).toBe('/favicon.ico');
		expect(resolveFaviconPath(legacyBranding, 'light')).toBe('/favicon.ico');
		expect(resolveFaviconPath({ favicon_path: '/api/custom-favicon.png' }, 'dark')).toBe('/api/custom-favicon.png');
	});
});
