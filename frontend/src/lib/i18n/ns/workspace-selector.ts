import type source from '../messages/ko/workspace-selector.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'workspace-selector',
  import.meta.glob<Record<string, string>>('../messages/*/workspace-selector.json', { eager: true, import: 'default' }),
);
