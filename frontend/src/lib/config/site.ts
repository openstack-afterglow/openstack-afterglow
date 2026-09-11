import { writable, get } from 'svelte/store';
import type { PublicSiteConfig } from '$lib/types/siteConfig';

export type SiteConfig = PublicSiteConfig;

export type SiteConfigPatch = Omit<Partial<PublicSiteConfig>, 'services' | 'runtime'> & {
	services?: Partial<PublicSiteConfig['services']>;
	runtime?: Partial<PublicSiteConfig['runtime']>;
};

const DEFAULTS: SiteConfig = {
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

export const siteConfig = writable<SiteConfig>({ ...DEFAULTS });

export function initSiteConfig(config: SiteConfigPatch): void {
	siteConfig.update((current) => ({
		...current,
		...config,
		services: { ...current.services, ...(config.services ?? {}) },
		runtime: { ...current.runtime, ...(config.runtime ?? {}) },
	}));
}

export function replaceSiteConfig(config: PublicSiteConfig): void {
	siteConfig.set({
		...config,
		services: { ...config.services },
		runtime: { ...config.runtime },
	});
}

export function qualifyBackendAssetPaths(config: Partial<PublicSiteConfig>, apiBase: string): Partial<PublicSiteConfig> {
	const qualify = (value: string | undefined) =>
		value?.startsWith('/api/') ? `${apiBase}${value}` : value;
	const next = { ...config };
	if (next.logo_path) next.logo_path = qualify(next.logo_path);
	if (next.logo_dark_path) next.logo_dark_path = qualify(next.logo_dark_path);
	if (next.logo_light_path) next.logo_light_path = qualify(next.logo_light_path);
	if (next.favicon_path) next.favicon_path = qualify(next.favicon_path);
	return next;
}

export function getSiteName(): string {
	return get(siteConfig).site_name;
}

export function getSiteDescription(): string {
	return get(siteConfig).site_description;
}
