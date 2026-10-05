import type source from '../messages/ko/chat-settings.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'chat-settings',
	import.meta.glob<Record<string, string>>('../messages/*/chat-settings.json', { eager: true, import: 'default' }),
);
