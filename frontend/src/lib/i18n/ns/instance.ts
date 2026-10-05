import type source from '../messages/ko/instance.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'instance',
	import.meta.glob<Record<string, string>>('../messages/*/instance.json', { eager: true, import: 'default' }),
);
