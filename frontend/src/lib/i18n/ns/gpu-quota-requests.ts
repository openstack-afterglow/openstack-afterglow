import type source from '../messages/ko/gpu-quota-requests.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'gpu-quota-requests',
	import.meta.glob<Record<string, string>>('../messages/*/gpu-quota-requests.json', { eager: true, import: 'default' }),
);
