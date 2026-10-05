import type source from '../messages/ko/drover.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'drover',
	import.meta.glob<Record<string, string>>('../messages/*/drover.json', { eager: true, import: 'default' }),
);
