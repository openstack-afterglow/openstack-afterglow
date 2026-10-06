import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { getDocGuides } from '$lib/docs/catalog';
import { docsMessages } from '$lib/docs/locales';

export const load: PageLoad = async ({ params, parent }) => {
	const { docsLocale } = await parent();
	const guides = await getDocGuides(docsLocale);
	const guide = guides.find((item) => item.slug === params.slug);
	if (!guide) error(404, docsMessages[docsLocale].notFound);
	return {
		guide,
		relatedGuides: guides.filter((item) => guide.related.includes(item.slug)),
	};
};
