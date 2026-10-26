import type source from '../messages/ko/palimpsest-assets.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'palimpsest-assets',
  import.meta.glob<Record<string, string>>('../messages/*/palimpsest-assets.json', { eager: true, import: 'default' }),
);
