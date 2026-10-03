import type source from '../messages/ko/palimpsest-packages.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'palimpsest-packages',
	import.meta.glob<Record<string, string>>('../messages/*/palimpsest-packages.json', { eager: true, import: 'default' }),
);
