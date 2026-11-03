import type source from '../messages/ko/admin-email.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-email',
	import.meta.glob<Record<string, string>>('../messages/*/admin-email.json', { eager: true, import: 'default' }),
);
