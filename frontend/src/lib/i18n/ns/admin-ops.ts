import type source from '../messages/ko/admin-ops.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-ops',
	import.meta.glob<Record<string, string>>('../messages/*/admin-ops.json', { eager: true, import: 'default' }),
);
