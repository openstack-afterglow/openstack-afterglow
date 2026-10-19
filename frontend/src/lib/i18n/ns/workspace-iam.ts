import type source from '../messages/ko/workspace-iam.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'workspace-iam',
	import.meta.glob<Record<string, string>>('../messages/*/workspace-iam.json', { eager: true, import: 'default' }),
);
