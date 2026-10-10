<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import type { AutoRefreshController } from '$lib/utils/autoRefresh.svelte';

  interface Props {
    logs: string;
    logsLoading: boolean;
    ar: AutoRefreshController;
    onManualRefresh: () => void;
  }

  let { logs, logsLoading, ar, onManualRefresh }: Props = $props();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4" aria-busy={logsLoading}>
  <div class="flex items-center justify-between mb-3">
    <div class="text-xs text-ink-2">{t('instances.logs.title')}</div>
    <AutoRefreshControl
      bind:active={ar.active}
      bind:intervalSeconds={ar.intervalSeconds}
      intervalOptions={ar.intervalOptions}
      refreshing={logsLoading}
      onManualRefresh={onManualRefresh}
    />
  </div>
  {#if logs}
    <pre class="bg-surface-canvas rounded p-3 text-xs text-ink-2 overflow-auto max-h-64 font-mono whitespace-pre-wrap">{logs}</pre>
  {:else}
    <div class="text-ink-2 text-xs">{t('instances.logs.refreshHint')}</div>
  {/if}
</div>
