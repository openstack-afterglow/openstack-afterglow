import type source from '../messages/ko/palimpsest-local.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'palimpsest-local',
  import.meta.glob<Record<string, string>>('../messages/*/palimpsest-local.json', { eager: true, import: 'default' }),
);
