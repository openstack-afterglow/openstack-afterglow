import type source from '../messages/ko/admin-compute.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-compute',
	import.meta.glob<Record<string, string>>('../messages/*/admin-compute.json', { eager: true, import: 'default' }),
);
