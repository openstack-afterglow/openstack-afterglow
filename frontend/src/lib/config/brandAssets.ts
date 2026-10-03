import type { PublicSiteConfig } from '$lib/types/siteConfig';

export type ResolvedBrandTheme = 'dark' | 'light';

export function resolveLandingLogoPath(
	config: Pick<PublicSiteConfig, 'logo_path' | 'logo_dark_path' | 'logo_light_path'>,
	theme: ResolvedBrandTheme,
): string {
	const configuredPath = theme === 'dark'
		? (config.logo_light_path || config.logo_path)
		: (config.logo_dark_path || config.logo_path);
	return !configuredPath || configuredPath === '/afterglow-logo.svg' ? '/afterglow-symbol.svg' : configuredPath;
}

export function resolveFaviconPath(
	config: Pick<PublicSiteConfig, 'favicon_path'>,
): string {
	return config.favicon_path || '/favicon.svg';
}
