import type source from '../messages/ko/images-keys.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'images-keys',
	import.meta.glob<Record<string, string>>('../messages/*/images-keys.json', { eager: true, import: 'default' }),
);
