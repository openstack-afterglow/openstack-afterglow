import type source from '../messages/ko/file-storage.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'file-storage',
	import.meta.glob<Record<string, string>>('../messages/*/file-storage.json', { eager: true, import: 'default' }),
);
