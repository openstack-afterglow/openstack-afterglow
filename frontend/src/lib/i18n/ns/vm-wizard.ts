import type source from '../messages/ko/vm-wizard.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'vm-wizard',
	import.meta.glob<Record<string, string>>('../messages/*/vm-wizard.json', { eager: true, import: 'default' }),
);
