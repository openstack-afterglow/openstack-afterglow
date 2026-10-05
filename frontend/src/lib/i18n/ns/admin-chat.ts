import type source from '../messages/ko/admin-chat.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-chat',
	import.meta.glob<Record<string, string>>('../messages/*/admin-chat.json', { eager: true, import: 'default' }),
);
