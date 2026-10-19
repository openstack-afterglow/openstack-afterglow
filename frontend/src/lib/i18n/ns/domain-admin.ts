import type source from '../messages/ko/domain-admin.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'domain-admin',
  import.meta.glob<Record<string, string>>('../messages/*/domain-admin.json', { eager: true, import: 'default' }),
);
