import type source from '../messages/ko/mcp-gallery.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'mcp-gallery',
	import.meta.glob<Record<string, string>>('../messages/*/mcp-gallery.json', { eager: true, import: 'default' }),
);
