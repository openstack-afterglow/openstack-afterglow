import type source from '../messages/ko/dashboard-home.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'dashboard-home',
	import.meta.glob<Record<string, string>>('../messages/*/dashboard-home.json', { eager: true, import: 'default' }),
);
