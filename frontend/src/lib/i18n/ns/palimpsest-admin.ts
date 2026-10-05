import type source from '../messages/ko/palimpsest-admin.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'palimpsest-admin',
	import.meta.glob<Record<string, string>>('../messages/*/palimpsest-admin.json', { eager: true, import: 'default' }),
);
