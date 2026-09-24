export interface PublicSiteConfig {
	site_name: string;
	site_description: string;
	logo_path: string;
	logo_dark_path: string;
	logo_light_path: string;
	favicon_path: string;
	refresh_interval_ms: number;
	mcp_url?: string;
	services: {
		magnum: boolean;
		manila: boolean;
		zun: boolean;
		cloud_shell: boolean;
		k3s: boolean;
		trove: boolean;
		swift: boolean;
		barbican: boolean;
		waygate: boolean;
		chat: boolean;
		mcp: boolean;
	};
	runtime: {
		api_base: string;
		s3_base: string;
		grafana_base: string;
		librechat_base: string;
		gitlab_base: string;
	};
}
