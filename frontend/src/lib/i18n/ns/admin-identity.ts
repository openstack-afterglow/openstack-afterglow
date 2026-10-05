import type source from '../messages/ko/admin-identity.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-identity',
	import.meta.glob<Record<string, string>>('../messages/*/admin-identity.json', { eager: true, import: 'default' }),
);
