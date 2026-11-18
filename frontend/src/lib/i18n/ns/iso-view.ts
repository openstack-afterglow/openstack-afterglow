import type source from '../messages/ko/iso-view.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'iso-view',
	import.meta.glob<Record<string, string>>('../messages/*/iso-view.json', { eager: true, import: 'default' }),
);
