import type source from '../messages/ko/object-storage.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'object-storage',
	import.meta.glob<Record<string, string>>('../messages/*/object-storage.json', { eager: true, import: 'default' }),
);
