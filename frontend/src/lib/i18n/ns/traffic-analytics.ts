import type source from '../messages/ko/traffic-analytics.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'traffic-analytics',
	import.meta.glob<Record<string, string>>('../messages/*/traffic-analytics.json', { eager: true, import: 'default' }),
);
