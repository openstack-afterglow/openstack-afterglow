import type source from '../messages/ko/containers-shell.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'containers-shell',
	import.meta.glob<Record<string, string>>('../messages/*/containers-shell.json', { eager: true, import: 'default' }),
);
