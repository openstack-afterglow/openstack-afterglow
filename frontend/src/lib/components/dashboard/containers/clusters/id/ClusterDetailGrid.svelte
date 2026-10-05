<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import type { Cluster } from '$lib/types/cluster';
  import { clusterStatusColor } from '$lib/types/cluster';

  let { cluster }: { cluster: Cluster } = $props();
</script>

<div class="grid grid-cols-2 gap-4 mb-6">
  <div class="bg-surface-base border border-line rounded-xl p-4">
    <div class="text-xs text-ink-2 mb-1">{t('clusters.detail.status')}</div>
    <span class="px-2 py-0.5 rounded text-xs font-medium {clusterStatusColor[cluster.status] ?? 'text-ink-2 bg-surface-sunken'}">{cluster.status}</span>
    {#if cluster.status_reason}
      <p class="text-xs text-ink-2 mt-2">{cluster.status_reason}</p>
    {/if}
  </div>
  <div class="bg-surface-base border border-line rounded-xl p-4">
    <div class="text-xs text-ink-2 mb-1">{t('clusters.detail.nodeConfiguration')}</div>
    <div class="text-ink-0 text-sm">{t('clusters.detail.nodeCounts', { masters: cluster.master_count, workers: cluster.node_count })}</div>
  </div>
  <div class="bg-surface-base border border-line rounded-xl p-4">
    <div class="text-xs text-ink-2 mb-1">{t('clusters.detail.apiAddress')}</div>
    <div class="text-ink-0 text-xs font-mono">{cluster.api_address ?? t('clusters.placeholder')}</div>
  </div>
  <div class="bg-surface-base border border-line rounded-xl p-4">
    <div class="text-xs text-ink-2 mb-1">{t('clusters.detail.coeVersion')}</div>
    <div class="text-ink-0 text-sm">{cluster.coe_version ?? t('clusters.placeholder')}</div>
  </div>
  <div class="bg-surface-base border border-line rounded-xl p-4">
    <div class="text-xs text-ink-2 mb-1">{t('clusters.detail.keypair')}</div>
    <div class="text-ink-0 text-sm">{cluster.keypair ?? t('clusters.placeholder')}</div>
  </div>
  <div class="bg-surface-base border border-line rounded-xl p-4">
    <div class="text-xs text-ink-2 mb-1">{t('clusters.detail.createdAt')}</div>
    <div class="text-ink-0 text-sm">{cluster.created_at?.slice(0, 19).replace('T', ' ') ?? t('clusters.placeholder')}</div>
  </div>
</div>
{#if cluster.api_address}
  <div class="bg-surface-base border border-line rounded-xl p-4">
    <div class="text-xs text-ink-2 mb-3">{t('clusters.detail.kubectlConfiguration')}</div>
    <pre class="bg-surface-canvas rounded p-3 text-xs text-green-300 overflow-auto">openstack coe cluster config {cluster.name} --dir ~/.kube --force</pre>
  </div>
{/if}
