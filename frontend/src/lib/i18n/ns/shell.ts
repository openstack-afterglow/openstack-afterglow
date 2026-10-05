import type source from '../messages/ko/shell.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'shell',
	import.meta.glob<Record<string, string>>('../messages/*/shell.json', { eager: true, import: 'default' }),
);
