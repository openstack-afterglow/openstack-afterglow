import type source from '../messages/ko/domain-auth.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'domain-auth',
  import.meta.glob<Record<string, string>>('../messages/*/domain-auth.json', { eager: true, import: 'default' }),
);
