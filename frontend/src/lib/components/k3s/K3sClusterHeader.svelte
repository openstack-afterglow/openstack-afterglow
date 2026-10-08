<script lang="ts">
  import { t } from '$lib/i18n/ns/drover';
  import { k3sPermissions } from '$lib/stores/k3sPermissions';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
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
    {#if s.cluster!.k3s_version}<span class="text-xs text-ink-2">{s.cluster!.k3s_version}</span>{/if}
    {#if s.cluster!.status_reason}<p class="text-xs text-ink-2">{s.cluster!.status_reason}</p>{/if}
  {/snippet}
  {#snippet actions()}
    {#if s.cluster!.status === 'CREATING' || s.cluster!.status === 'PROVISIONING'}
      <ActivityIndicator variant="pulse" size="xs" label={t('overview.header.initializing')} class="text-xs" />
    {:else if s.cluster!.status === 'ACTIVE'}
      <button
        onclick={() => s.triggerHealthCheck()}
        disabled={!$k3sPermissions.inventory || s.checkingHealth}
        class="px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-1 text-xs rounded-lg transition-colors disabled:opacity-50">
        {#if s.checkingHealth}<ActivityIndicator size="xs" label={t('overview.header.checking')} />{:else}{t('overview.header.healthCheck')}{/if}
      </button>
      <K3sCloudShellButton />
      <Button onclick={() => s.downloadKubeconfig()} disabled={!$k3sPermissions.credentials} size="sm">
        {t('overview.header.downloadKubeconfig')}
      </Button>
      {#if $k3sPermissions.adminCredentials && !s.adminMode}
        <Button onclick={() => s.downloadKubeconfig(true)} variant="danger-outline" size="sm">
          {t('overview.header.downloadAdminKubeconfig')}
        </Button>
      {/if}
    {/if}
    <button onclick={() => s.deleteCluster()} disabled={!$k3sPermissions.administerClusters || s.deleting}
      class="px-3 py-1.5 bg-red-900/40 hover:bg-red-900/60 border border-red-800 text-red-400 text-xs rounded-lg transition-colors disabled:opacity-50">
      {#if s.deleting}<ActivityIndicator size="xs" label={t('overview.header.deleting')} />{:else}{t('overview.header.deleteCluster')}{/if}
    </button>
  {/snippet}
</DetailHeader>
