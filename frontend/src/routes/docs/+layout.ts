import type { LayoutLoad } from './$types';
import { getDocGuides } from '$lib/docs/catalog';
import { docsLocaleFromUrl } from '$lib/docs/locales';

export const load: LayoutLoad = async ({ url, parent }) => {
	const { locale } = await parent();
	const docsLocale = docsLocaleFromUrl(url, locale);
	const guides = await getDocGuides(docsLocale);
	return {
		docsLocale,
		docsNavigationGuides: guides.map(({ slug, name, category }) => ({ slug, name, category })),
	};
};
