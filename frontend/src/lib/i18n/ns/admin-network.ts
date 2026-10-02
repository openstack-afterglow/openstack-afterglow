import type source from '../messages/ko/admin-network.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-network',
	import.meta.glob<Record<string, string>>('../messages/*/admin-network.json', { eager: true, import: 'default' }),
);
