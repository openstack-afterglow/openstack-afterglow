import { MOCKUP_QUERY_KEY } from '$lib/mockup/contracts';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ locals, url }) => {
	// Depend on the query so client navigation between mock profiles re-runs this load.
	void url.searchParams.get(MOCKUP_QUERY_KEY);
	return { locale: locals.locale, mockup: locals.mockup, siteConfig: locals.siteConfig };
};
