import type source from '../messages/ko/palimpsest-catalog.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'palimpsest-catalog',
  import.meta.glob<Record<string, string>>('../messages/*/palimpsest-catalog.json', { eager: true, import: 'default' }),
);
