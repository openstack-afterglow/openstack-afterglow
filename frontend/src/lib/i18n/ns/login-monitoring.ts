import type source from '../messages/ko/login-monitoring.json';
import { defineMessages } from '../runtime.svelte';

export const t = defineMessages<typeof source>(
  'login-monitoring',
  import.meta.glob<Record<string, string>>('../messages/*/login-monitoring.json', { eager: true, import: 'default' }),
);
