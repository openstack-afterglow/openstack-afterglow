import { readFileSync } from 'fs';
import { parse } from 'smol-toml';
import type { PublicSiteConfig } from '$lib/types/siteConfig';

const DEFAULTS: PublicSiteConfig = {
	site_name: 'Afterglow',
	site_description: 'OpenStack VM + OverlayFS 배포 플랫폼',
	logo_path: '/logo.png',
	logo_dark_path: '/logo-white.png',
	logo_light_path: '/logo-dark.png',
	favicon_path: '/favicon.ico',
	refresh_interval_ms: 5000,
	services: { magnum: false, manila: false, zun: false, cloud_shell: false, k3s: false, trove: false, swift: false, barbican: false, waygate: false, chat: false, mcp: false },
	mcp_url: '',
	runtime: {
		api_base: 'http://localhost:8000',
		s3_base: '',
		grafana_base: '',
		librechat_base: '',
		gitlab_base: '',
	},
};

function findConfigPath(): string | null {
	const candidates = [
		process.cwd() + '/afterglow.conf',
		process.cwd() + '/../afterglow.conf',
		process.cwd() + '/config.toml',
		process.cwd() + '/../config.toml',
		'/app/afterglow.conf',
		'/app/config.toml',
		'/app/afterglow.toml',
		process.cwd() + '/afterglow.toml',
	];
	for (const p of candidates) {
		try {
			readFileSync(p);
			return p;
		} catch {
			// try next
		}
	}
	return null;
}

function stringOrEmpty(value: unknown): string {
	return typeof value === 'string' ? value.trim() : '';
}

function originOf(value: string): string {
	if (!value) return '';
	try {
		return new URL(value).origin;
	} catch {
		return '';
	}
}

function portFrom(value: unknown, fallback: number): number {
	const num = Number(value);
	return Number.isFinite(num) && num > 0 ? num : fallback;
}

export function deriveBrowserApiBase(app: Record<string, unknown>, env: Record<string, string | undefined> = process.env): string {
	const publicApiEnvOrigin = originOf(stringOrEmpty(env.PUBLIC_API_BASE));
	if (publicApiEnvOrigin) return publicApiEnvOrigin;

	const publicApiOrigin = originOf(stringOrEmpty(app.public_api_base));
	if (publicApiOrigin) return publicApiOrigin;

	const frontendOrigin = originOf(stringOrEmpty(app.frontend_base_url));
	if (frontendOrigin) return frontendOrigin;

	const backendPort = portFrom(app.backend_port, 8000);
	return `http://localhost:${backendPort}`;
}


function mcpPublicUrl(value: unknown): string {
	const raw = stringOrEmpty(value);
	if (!raw) return '';
	try {
		const url = new URL(raw);
		if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return '';
		url.pathname = url.pathname.replace(/\/+$/, '') || '/api/v1/mcp';
		return url.toString().replace(/\/+$/, '');
	} catch {
		return '';
	}
}

function fallbackPublicSiteConfig(): PublicSiteConfig {
	return {
		...DEFAULTS,
		services: { ...DEFAULTS.services },
		runtime: { ...DEFAULTS.runtime, api_base: deriveBrowserApiBase({}) },
	};
}

let _cached: PublicSiteConfig | null = null;

export function loadPublicSiteConfig(): PublicSiteConfig {
	if (_cached) return _cached;
	const configPath = findConfigPath();


	if (!configPath) {
		_cached = fallbackPublicSiteConfig();
		return _cached;
	}

	try {
		const raw = readFileSync(configPath, 'utf-8');
		const toml = parse(raw) as Record<string, unknown>;

		const app = (toml.app ?? {}) as Record<string, unknown>;
		const services = (toml.services ?? {}) as Record<string, unknown>;
		const openstack = (toml.openstack ?? {}) as Record<string, unknown>;
		const monitoring = (toml.monitoring ?? {}) as Record<string, unknown>;
		const chat = (toml.chat ?? {}) as Record<string, unknown>;
		const gitlabOidc = (toml.gitlab_oidc ?? {}) as Record<string, unknown>;
		const mcp = (toml.mcp ?? {}) as Record<string, unknown>;

		_cached = {
			site_name: String(app.site_name ?? DEFAULTS.site_name),
			site_description: String(app.site_description ?? DEFAULTS.site_description),
			logo_path: String(app.logo_path ?? DEFAULTS.logo_path),
			logo_dark_path: String(app.logo_dark_path ?? DEFAULTS.logo_dark_path),
			logo_light_path: String(app.logo_light_path ?? DEFAULTS.logo_light_path),
			favicon_path: String(app.favicon_path ?? DEFAULTS.favicon_path),
			refresh_interval_ms: Number(app.refresh_interval_ms ?? DEFAULTS.refresh_interval_ms),
			mcp_url: mcpPublicUrl(mcp.public_url),
			services: {
				magnum: Boolean(services.magnum ?? false),
				manila: Boolean(services.manila ?? false),
				zun: Boolean(services.zun ?? false),
				cloud_shell: Boolean(services.cloud_shell ?? false) && Boolean(services.zun ?? false),
				k3s: Boolean(services.k3s ?? false),
				trove: Boolean(services.trove ?? false),
				swift: Boolean(services.swift ?? false),
				barbican: Boolean(services.barbican ?? false),
				waygate: Boolean(services.waygate ?? false),
				chat: Boolean(services.chat ?? false),
				mcp: Boolean(services.mcp ?? false),
			},
			runtime: {
				api_base: deriveBrowserApiBase(app),
				s3_base: originOf(stringOrEmpty(openstack.s3_endpoint)),
				grafana_base: originOf(stringOrEmpty(monitoring.grafana_base_url)),
				librechat_base: originOf(stringOrEmpty(chat.base_url)),
				// GitLab OIDC 활성화 시에만 노출 — LibreChat이 임베드된 프레임 안에서
				// GitLab로 자체 리다이렉트할 때 frame-src가 이를 막지 않도록 함.
				gitlab_base: Boolean(gitlabOidc.enabled ?? false)
					? originOf(stringOrEmpty(gitlabOidc.gitlab_url))
					: '',
			},
		};
	} catch {
		console.warn("Unable to load Afterglow frontend runtime configuration; using public environment fallback.");
		_cached = fallbackPublicSiteConfig();
	}

	return _cached;
}
