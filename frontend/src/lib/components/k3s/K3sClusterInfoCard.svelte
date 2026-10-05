<script lang="ts">
  import { t } from '$lib/i18n/ns/drover';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import { auth } from '$lib/stores/auth';
  import { api } from '$lib/api/client';
  import { downloadBlobAs } from '$lib/utils/downloadBlob';
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
  import K3sCertificateExpiryModal from '$lib/components/k3s/K3sCertificateExpiryModal.svelte';

  const s = useK3sClusterDetailController();
  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  let showCertModal = $state(false);
  let downloadingCa = $state(false);

  async function downloadCa() {
    if (!s.cluster) return;
    downloadingCa = true;
    try {
      const { blob } = await api.downloadBlob(
        `/api/v1/k3s/clusters/${s.cluster.id}/ca-certificate`,
        token,
        projectId,
      );
      downloadBlobAs(blob, `ca-${s.cluster.name}.pem`);
    } catch (e) {
      console.error(t('overview.info.caDownloadFailed'), e);
    } finally {
      downloadingCa = false;
    }
  }
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
  <h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('overview.info.title')}</h3>
  <dl class="space-y-1.5 text-sm">
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">{t('overview.info.id')}</dt>
      <dd class="font-mono text-xs text-ink-2">{s.cluster!.id.slice(0, 12)}...</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">{t('overview.info.apiAddress')}</dt>
      <dd class="text-ink-2 font-mono text-xs">{s.cluster!.api_address || t('overview.notAvailable')}</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">{t('overview.info.serverIp')}</dt>
      <dd class="text-ink-2 font-mono text-xs">{s.cluster!.server_ip || t('overview.notAvailable')}</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">{t('overview.info.keyPair')}</dt>
      <dd class="text-ink-2 text-xs">{s.cluster!.key_name || t('overview.notAvailable')}</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">{t('overview.info.stampede')}</dt>
      <dd class="text-xs">
        {#if s.cluster!.stampede_enabled}
          <span class="text-warm-text">{t('overview.info.enabled')}</span>
        {:else}
          <span class="text-ink-2">{t('overview.info.disabled')}</span>
        {/if}
      </dd>
    </div>
    <div class="flex justify-between items-center">
      <dt class="text-ink-2 text-xs">{t('overview.info.certificate')}</dt>
      <dd class="flex gap-1.5">
        <button
          onclick={downloadCa}
          disabled={downloadingCa}
          class="text-xs px-2 py-0.5 rounded bg-surface-selected hover:bg-surface-selected text-ink-1 disabled:opacity-50 transition-colors"
        >
          {downloadingCa ? t('overview.pending') : t('overview.info.downloadCa')}
        </button>
        <button
          onclick={() => (showCertModal = true)}
          class="text-xs px-2 py-0.5 rounded bg-surface-selected hover:bg-surface-selected text-ink-1 transition-colors"
        >
          {t('overview.info.checkExpiry')}
        </button>
      </dd>
    </div>
    {#if s.health}
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">{t('overview.info.apiServer')}</dt>
        <dd class="text-xs {s.health.api_server_reachable ? 'text-green-400' : 'text-red-400'}">
          {s.health.api_server_reachable ? t('overview.info.reachable') : t('overview.info.unreachable')}
        </dd>
      </div>
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">{t('overview.info.healthz')}</dt>
        <dd class="text-xs {s.health.healthz_ok ? 'text-green-400' : 'text-red-400'}">
          {s.health.healthz_ok ? t('overview.info.ok') : t('overview.info.fail')}
        </dd>
      </div>
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">{t('overview.info.checkedAt')}</dt>
        <dd class="text-ink-2 text-xs">{new Date(s.health.checked_at).toLocaleTimeString(intlLocale())}</dd>
      </div>
    {/if}
  </dl>
</div>

{#if showCertModal && s.cluster}
  <K3sCertificateExpiryModal
    clusterId={s.cluster.id}
    clusterName={s.cluster.name}
    {token}
    {projectId}
    onclose={() => (showCertModal = false)}
  />
{/if}
