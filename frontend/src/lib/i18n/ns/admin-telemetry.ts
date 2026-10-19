import type source from '../messages/ko/admin-telemetry.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
	'admin-telemetry',
	import.meta.glob<Record<string, string>>('../messages/*/admin-telemetry.json', { eager: true, import: 'default' }),
);
