import type source from '../messages/ko/chat-diagnostics.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'chat-diagnostics',
	import.meta.glob<Record<string, string>>('../messages/*/chat-diagnostics.json', { eager: true, import: 'default' }),
);
