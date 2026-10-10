import type { PageLoad } from './$types';
import { getDocGuides } from '$lib/docs/catalog';

export const load: PageLoad = async ({ parent }) => {
	const { docsLocale } = await parent();
	return { guides: await getDocGuides(docsLocale) };
};
