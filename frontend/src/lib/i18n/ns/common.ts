import type source from '../messages/ko/common.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'common',
	import.meta.glob<Record<string, string>>('../messages/*/common.json', { eager: true, import: 'default' }),
);
