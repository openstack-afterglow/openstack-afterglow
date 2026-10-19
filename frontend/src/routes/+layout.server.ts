import { MOCKUP_QUERY_KEY } from '$lib/mockup/contracts';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ locals, url, depends }) => {
	depends('afterglow:locale');
	// Depend on the query so client navigation between mock profiles re-runs this load.
	void url.searchParams.get(MOCKUP_QUERY_KEY);
	// Refresh the cookie-backed locale on route/language changes, even when this layout is reused.
	void url.pathname;
	void url.searchParams.get('lang');
	return { locale: locals.locale, mockup: locals.mockup, siteConfig: locals.siteConfig };
};
