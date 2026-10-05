import type source from '../messages/ko/topology.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'topology',
	import.meta.glob<Record<string, string>>('../messages/*/topology.json', { eager: true, import: 'default' }),
);
