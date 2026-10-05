import type source from '../messages/ko/shared.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'shared',
	import.meta.glob<Record<string, string>>('../messages/*/shared.json', { eager: true, import: 'default' }),
);
