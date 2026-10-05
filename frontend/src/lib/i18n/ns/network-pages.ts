import type source from '../messages/ko/network-pages.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'network-pages',
	import.meta.glob<Record<string, string>>('../messages/*/network-pages.json', { eager: true, import: 'default' }),
);
