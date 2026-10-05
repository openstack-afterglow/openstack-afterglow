import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ params }) => {
	const workspaceId = Number(params.id);
	if (!Number.isSafeInteger(workspaceId) || workspaceId < 1) error(404);
	return { workspaceId };
};
