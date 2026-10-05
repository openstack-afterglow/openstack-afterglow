import type source from '../messages/ko/chat-studio.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'chat-studio',
	import.meta.glob<Record<string, string>>('../messages/*/chat-studio.json', { eager: true, import: 'default' }),
);
