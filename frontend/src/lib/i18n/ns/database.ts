import type source from '../messages/ko/database.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'database',
	import.meta.glob<Record<string, string>>('../messages/*/database.json', { eager: true, import: 'default' }),
);
