import type source from '../messages/ko/vpn-reserved-ranges.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'vpn-reserved-ranges',
  import.meta.glob<Record<string, string>>('../messages/*/vpn-reserved-ranges.json', { eager: true, import: 'default' }),
);
