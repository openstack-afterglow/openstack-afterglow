<script lang="ts">
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
  import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import K3sCloudShellButton from './K3sCloudShellButton.svelte';

  const s = useK3sClusterDetailController();
</script>

<DetailHeader
  title={s.cluster!.name}
  status={s.cluster!.status}
  secondaryStatus={s.health?.status ?? null}
>
  {#snippet meta()}
    {#if s.cluster!.k3s_version}<span class="text-xs text-ink-3">{s.cluster!.k3s_version}</span>{/if}
    {#if s.cluster!.status_reason}<p class="text-xs text-ink-3">{s.cluster!.status_reason}</p>{/if}
  {/snippet}
  {#snippet actions()}
    {#if s.cluster!.status === 'CREATING' || s.cluster!.status === 'PROVISIONING'}
      <div class="flex items-center gap-1.5 text-yellow-400 text-xs">
        <span class="animate-pulse">●</span>
        <span>초기화 중...</span>
      </div>
    {:else if s.cluster!.status === 'ACTIVE'}
      <button
        onclick={() => s.triggerHealthCheck()}
        disabled={s.checkingHealth}
        class="px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-1 text-xs rounded-lg transition-colors disabled:opacity-50">
        {s.checkingHealth ? '확인 중...' : '헬스 체크'}
      </button>
      <K3sCloudShellButton />
      <Button onclick={() => s.downloadKubeconfig()} size="sm">
        kubeconfig 다운로드
      </Button>
    {/if}
    <button onclick={() => s.deleteCluster()} disabled={s.deleting}
      class="px-3 py-1.5 bg-red-900/40 hover:bg-red-900/60 border border-red-800 text-red-400 text-xs rounded-lg transition-colors disabled:opacity-50">
      {s.deleting ? '삭제 중...' : '클러스터 삭제'}
    </button>
  {/snippet}
</DetailHeader>
