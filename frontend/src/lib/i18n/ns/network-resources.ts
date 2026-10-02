import type source from '../messages/ko/network-resources.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'network-resources',
	import.meta.glob<Record<string, string>>('../messages/*/network-resources.json', { eager: true, import: 'default' }),
);
