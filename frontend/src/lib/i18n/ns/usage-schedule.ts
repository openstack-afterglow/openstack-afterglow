import type source from '../messages/ko/usage-schedule.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'usage-schedule',
	import.meta.glob<Record<string, string>>('../messages/*/usage-schedule.json', { eager: true, import: 'default' }),
);
