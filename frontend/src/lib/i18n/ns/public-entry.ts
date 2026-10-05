import type source from '../messages/ko/public-entry.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'public-entry',
	import.meta.glob<Record<string, string>>('../messages/*/public-entry.json', { eager: true, import: 'default' }),
);
