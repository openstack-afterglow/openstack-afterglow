import type { LayoutLoad } from './$types';
import { getDocGuides } from '$lib/docs/catalog';
import { docsLocaleFromUrl } from '$lib/docs/locales';

export const load: LayoutLoad = async ({ url }) => {
	const docsLocale = docsLocaleFromUrl(url);
	const guides = await getDocGuides(docsLocale);
	return {
		docsLocale,
		docsNavigationGuides: guides.map(({ slug, name, category }) => ({ slug, name, category })),
	};
};
