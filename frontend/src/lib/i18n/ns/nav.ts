import type source from '../messages/ko/nav.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'nav',
	import.meta.glob<Record<string, string>>('../messages/*/nav.json', { eager: true, import: 'default' }),
);
