import type source from '../messages/ko/native-providers.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'native-providers',
	import.meta.glob<Record<string, string>>('../messages/*/native-providers.json', { eager: true, import: 'default' }),
);
