import type source from '../messages/ko/volume.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'volume',
	import.meta.glob<Record<string, string>>('../messages/*/volume.json', { eager: true, import: 'default' }),
);
