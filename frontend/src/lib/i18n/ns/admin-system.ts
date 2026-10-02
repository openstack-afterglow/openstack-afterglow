import type source from '../messages/ko/admin-system.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-system',
	import.meta.glob<Record<string, string>>('../messages/*/admin-system.json', { eager: true, import: 'default' }),
);
