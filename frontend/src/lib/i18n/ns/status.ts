import type source from '../messages/ko/status.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'status',
	import.meta.glob<Record<string, string>>('../messages/*/status.json', { eager: true, import: 'default' }),
);
