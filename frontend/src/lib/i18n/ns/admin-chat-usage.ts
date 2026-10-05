import type source from '../messages/ko/admin-chat-usage.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-chat-usage',
	import.meta.glob<Record<string, string>>('../messages/*/admin-chat-usage.json', { eager: true, import: 'default' }),
);
