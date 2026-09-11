import type { ChatSettingsSection } from '$lib/components/chat/ChatSettingsOverlay.svelte';
import type { PageLoad } from './$types';

const SECTIONS = new Set<ChatSettingsSection>([
	'usage',
	'apikeys',
	'memory',
	'mcp',
	'tools',
	'skills'
]);

export const load: PageLoad = ({ url }) => {
	const requested = url.searchParams.get('section') as ChatSettingsSection | null;
	return { section: requested && SECTIONS.has(requested) ? requested : 'usage' };
};
