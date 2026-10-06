<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import { t as tc } from '$lib/i18n/ns/common';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import type { ZunContainerDetail } from '$lib/types/zunContainer';

  interface Props {
    container: ZunContainerDetail;
    actioning: boolean;
    terminalOpen: boolean;
    onOpenTerminal: () => void;
    onStart: () => Promise<void>;
    onStop: () => Promise<void>;
    onDelete: () => Promise<void>;
    onBack: () => void;
  }

  let { container, actioning, terminalOpen, onOpenTerminal, onStart, onStop, onDelete, onBack }: Props = $props();
</script>

<div class="flex items-center gap-3 mb-6">
  <button onclick={onBack} class="text-ink-2 hover:text-ink-0 transition-colors">{t('instances.detail.back')}</button>
</div>

<div class="flex items-start justify-between mb-6">
  <div>
    <h1 class="text-2xl font-bold text-ink-0">{container.name}</h1>
    <p class="text-ink-2 text-sm mt-1 font-mono">{container.uuid}</p>
  </div>
  <div class="flex gap-2">
    {#if actioning}<ActivityIndicator size="xs" label={tc('state.processing')} class="text-xs" />{/if}
    {#if container.status === 'Running'}
      <button onclick={onOpenTerminal} disabled={terminalOpen} class="px-4 py-2 text-sm text-warm-text border border-action-warm hover:bg-surface-selected/30 rounded-lg transition-colors disabled:opacity-40">{t('instances.terminal.title')}</button>
      <button onclick={onStop} disabled={actioning} class="px-4 py-2 text-sm text-orange-400 border border-orange-800 hover:bg-orange-900/30 rounded-lg transition-colors disabled:opacity-40">{t('instances.actions.stop')}</button>
    {:else if container.status === 'Stopped' || container.status === 'Created'}
      <button onclick={onStart} disabled={actioning} class="px-4 py-2 text-sm text-green-400 border border-green-800 hover:bg-green-900/30 rounded-lg transition-colors disabled:opacity-40">{t('instances.actions.start')}</button>
    {/if}
    <button onclick={onDelete} class="px-4 py-2 text-sm text-red-400 border border-red-800 hover:bg-red-900/30 rounded-lg transition-colors">{t('instances.actions.delete')}</button>
  </div>
</div>
