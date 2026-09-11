<script lang="ts">
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
      console.error('CA 다운로드 실패:', e);
    } finally {
      downloadingCa = false;
    }
  }
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
  <h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">클러스터 정보</h3>
  <dl class="space-y-1.5 text-sm">
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">ID</dt>
      <dd class="font-mono text-xs text-ink-2">{s.cluster!.id.slice(0, 12)}...</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">API 주소</dt>
      <dd class="text-ink-2 font-mono text-xs">{s.cluster!.api_address || '-'}</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">서버 IP</dt>
      <dd class="text-ink-2 font-mono text-xs">{s.cluster!.server_ip || '-'}</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">키페어</dt>
      <dd class="text-ink-2 text-xs">{s.cluster!.key_name || '-'}</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-ink-2 text-xs">Stampede</dt>
      <dd class="text-xs">
        {#if s.cluster!.stampede_enabled}
          <span class="text-action-warm">⚡ 활성</span>
        {:else}
          <span class="text-ink-3">비활성</span>
        {/if}
      </dd>
    </div>
    <div class="flex justify-between items-center">
      <dt class="text-ink-2 text-xs">인증서</dt>
      <dd class="flex gap-1.5">
        <button
          onclick={downloadCa}
          disabled={downloadingCa}
          class="text-xs px-2 py-0.5 rounded bg-surface-selected hover:bg-surface-selected text-ink-1 disabled:opacity-50 transition-colors"
        >
          {downloadingCa ? '...' : 'CA 다운로드'}
        </button>
        <button
          onclick={() => (showCertModal = true)}
          class="text-xs px-2 py-0.5 rounded bg-surface-selected hover:bg-surface-selected text-ink-1 transition-colors"
        >
          만료 조회
        </button>
      </dd>
    </div>
    {#if s.health}
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">API 서버</dt>
        <dd class="text-xs {s.health.api_server_reachable ? 'text-green-400' : 'text-red-400'}">
          {s.health.api_server_reachable ? '접근 가능' : '접근 불가'}
        </dd>
      </div>
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">healthz</dt>
        <dd class="text-xs {s.health.healthz_ok ? 'text-green-400' : 'text-red-400'}">
          {s.health.healthz_ok ? 'OK' : 'FAIL'}
        </dd>
      </div>
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">체크 시각</dt>
        <dd class="text-ink-2 text-xs">{new Date(s.health.checked_at).toLocaleTimeString('ko-KR')}</dd>
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
