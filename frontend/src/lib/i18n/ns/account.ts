import type source from '../messages/ko/account.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'account',
	import.meta.glob<Record<string, string>>('../messages/*/account.json', { eager: true, import: 'default' }),
);
