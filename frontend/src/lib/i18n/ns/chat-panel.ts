import type source from '../messages/ko/chat-panel.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'chat-panel',
	import.meta.glob<Record<string, string>>('../messages/*/chat-panel.json', { eager: true, import: 'default' }),
);
