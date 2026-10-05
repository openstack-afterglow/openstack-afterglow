import type source from '../messages/ko/waygate.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'waygate',
	import.meta.glob<Record<string, string>>('../messages/*/waygate.json', { eager: true, import: 'default' }),
);
