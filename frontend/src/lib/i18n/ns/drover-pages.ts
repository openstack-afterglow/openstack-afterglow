import type source from '../messages/ko/drover-pages.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'drover-pages',
	import.meta.glob<Record<string, string>>('../messages/*/drover-pages.json', { eager: true, import: 'default' }),
);
