import type { Locale } from '$lib/i18n/locales';
import type { MockupSession } from '$lib/mockup/contracts';
import type { PublicSiteConfig } from '$lib/types/siteConfig';

// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			locale: Locale;
			mockup: MockupSession;
			siteConfig: PublicSiteConfig;
		}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}

	const __APP_VERSION__: string;
}

export {};
