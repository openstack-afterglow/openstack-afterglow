import type source from '../messages/ko/admin-storage.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-storage',
	import.meta.glob<Record<string, string>>('../messages/*/admin-storage.json', { eager: true, import: 'default' }),
);
