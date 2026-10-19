import type source from '../messages/ko/palimpsest-hub.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'palimpsest-hub',
  import.meta.glob<Record<string, string>>('../messages/*/palimpsest-hub.json', { eager: true, import: 'default' }),
);
