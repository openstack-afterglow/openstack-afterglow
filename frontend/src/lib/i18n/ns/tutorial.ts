import type source from '../messages/ko/tutorial.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'tutorial',
	import.meta.glob<Record<string, string>>('../messages/*/tutorial.json', { eager: true, import: 'default' }),
);
