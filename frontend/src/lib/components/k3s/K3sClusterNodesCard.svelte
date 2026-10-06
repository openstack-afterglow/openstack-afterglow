<script lang="ts">
  import { t } from '$lib/i18n/ns/drover';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';
  import { useK3sClusterDetailController, healthColor } from '$lib/stores/k3sClusterDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';

  const s = useK3sClusterDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-xs text-ink-2 uppercase tracking-wide">{t('nodes.title')}</h3>
    {#if s.health}
      <div class="flex items-center gap-2">
        <span class="px-2 py-0.5 rounded border text-xs font-medium {healthColor[s.health.status] ?? 'text-ink-2 bg-surface-sunken border-line-2'}">
          {s.health.status}
        </span>
        <span class="text-xs text-ink-2">{new Date(s.health.checked_at).toLocaleTimeString(intlLocale())}</span>
      </div>
    {:else}
      <span class="text-xs text-ink-2">{t('nodes.unchecked')}</span>
    {/if}
  </div>

  {#if s.health && s.health.nodes.length > 0}
    <div class="space-y-2">
      {#each s.health.nodes as node}
        <div class="flex items-center justify-between py-1.5 border-b border-line last:border-0">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full {node.ready ? 'bg-green-400' : 'bg-red-400'}"></span>
            <span class="text-xs text-ink-2 font-mono">{node.name}</span>
            <span class="text-xs px-1.5 py-0.5 rounded {node.role === 'server' ? 'bg-purple-900/40 text-purple-400 border border-purple-800' : 'bg-surface-selected/40 text-warm-text border border-action-warm'}">
              {node.role}
            </span>
          </div>
          <div class="text-right">
            <span class="text-xs {node.ready ? 'text-green-400' : 'text-red-400'}">
              {node.ready ? 'Ready' : 'NotReady'}
            </span>
            {#if node.kubelet_version}
              <div class="text-xs text-ink-2 font-mono">{node.kubelet_version}</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>

    {#if s.cluster!.status === 'ACTIVE'}
      <div class="flex items-center gap-1.5 mt-3 pt-3 border-t border-line">
        <span class="text-ink-2 text-xs">{t('nodes.agents')}</span>
        <button
          onclick={() => s.decrementScale()}
          class="w-5 h-5 flex items-center justify-center bg-surface-selected hover:bg-surface-selected text-ink-0 rounded text-xs transition-colors">−</button>
        <span class="text-ink-2 text-xs min-w-[2rem] text-center">
          <AnimatedNumber value={s.cluster!.agent_vm_ids.length} /> / {s.scalingTarget ?? s.cluster!.agent_count}
        </span>
        <button
          onclick={() => s.incrementScale()}
          class="w-5 h-5 flex items-center justify-center bg-surface-selected hover:bg-surface-selected text-ink-0 rounded text-xs transition-colors">+</button>
        {#if s.scalingTarget !== null && s.scalingTarget !== s.cluster!.agent_count}
          <Button onclick={() => s.applyScale()} disabled={s.scaling} size="sm" class="ml-1">
            {#if s.scaling}<ActivityIndicator size="xs" label={t('scale.applying')} />{:else}{t('nodes.apply')}{/if}
          </Button>
        {/if}
      </div>
      {#if s.scaleError}
        <p class="text-red-400 text-xs mt-1">{s.scaleError}</p>
      {/if}
    {/if}
  {:else}
    <dl class="space-y-1.5 text-sm">
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">{t('nodes.server')}</dt>
        <dd class="text-ink-2 text-xs">1</dd>
      </div>
      <div class="flex justify-between items-center">
        <dt class="text-ink-2 text-xs">{t('nodes.worker')}</dt>
        <dd class="flex items-center gap-1.5">
          {#if s.cluster!.status === 'ACTIVE'}
            <button
              onclick={() => s.decrementScale()}
              class="w-5 h-5 flex items-center justify-center bg-surface-selected hover:bg-surface-selected text-ink-0 rounded text-xs transition-colors">−</button>
            <span class="text-ink-2 text-xs min-w-[2rem] text-center">
              <AnimatedNumber value={s.cluster!.agent_vm_ids.length} /> / {s.scalingTarget ?? s.cluster!.agent_count}
            </span>
            <button
              onclick={() => s.incrementScale()}
              class="w-5 h-5 flex items-center justify-center bg-surface-selected hover:bg-surface-selected text-ink-0 rounded text-xs transition-colors">+</button>
            {#if s.scalingTarget !== null && s.scalingTarget !== s.cluster!.agent_count}
              <Button onclick={() => s.applyScale()} disabled={s.scaling} size="sm" class="ml-1">
                {#if s.scaling}<ActivityIndicator size="xs" label={t('scale.applying')} />{:else}{t('nodes.apply')}{/if}
              </Button>
            {/if}
          {:else}
            <span class="text-ink-2 text-xs">{t('nodes.createdAgents', { created: s.cluster!.agent_vm_ids.length, total: s.cluster!.agent_count })}</span>
          {/if}
        </dd>
      </div>
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">{t('nodes.createdAt')}</dt>
        <dd class="text-ink-2 text-xs">{s.cluster!.created_at ? s.cluster!.created_at.split('T')[0] : '-'}</dd>
      </div>
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">{t('nodes.updatedAt')}</dt>
        <dd class="text-ink-2 text-xs">{s.cluster!.updated_at ? s.cluster!.updated_at.split('T')[0] : '-'}</dd>
      </div>
    </dl>
    {#if s.health === null && s.cluster!.status === 'ACTIVE'}
      <p class="text-xs text-ink-2 mt-2">{t('nodes.loadingHealth')}</p>
    {/if}
    {#if s.scaleError}
      <p class="text-red-400 text-xs mt-2">{s.scaleError}</p>
    {/if}
  {/if}
</div>
