import type source from '../messages/ko/domain-iam-groups.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'domain-iam-groups',
	import.meta.glob<Record<string, string>>('../messages/*/domain-iam-groups.json', { eager: true, import: 'default' }),
);
