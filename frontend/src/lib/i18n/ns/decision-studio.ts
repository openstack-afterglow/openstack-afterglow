import type source from '../messages/ko/decision-studio.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'decision-studio',
	import.meta.glob<Record<string, string>>('../messages/*/decision-studio.json', { eager: true, import: 'default' }),
);
