import type source from '../messages/ko/infra-topology.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'infra-topology',
	import.meta.glob<Record<string, string>>('../messages/*/infra-topology.json', { eager: true, import: 'default' }),
);
