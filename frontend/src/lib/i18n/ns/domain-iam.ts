import type source from '../messages/ko/domain-iam.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'domain-iam',
	import.meta.glob<Record<string, string>>('../messages/*/domain-iam.json', { eager: true, import: 'default' }),
);
