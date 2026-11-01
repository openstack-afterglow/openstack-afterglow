import type source from '../messages/ko/compute-pools.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'compute-pools',
  import.meta.glob<Record<string, string>>('../messages/*/compute-pools.json', { eager: true, import: 'default' }),
);
