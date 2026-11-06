<script lang="ts">
  import { t } from '$lib/i18n/ns/admin-ops';
  import { auth } from '$lib/stores/auth';
  import type { Service, NetworkAgent, EndpointGroup, StoragePool, TabKey } from '$lib/types/adminServices';
  import ServiceTable from './ServiceTable.svelte';
  import NetworkAgentTable from './NetworkAgentTable.svelte';
  import EndpointsTable from './EndpointsTable.svelte';
  import StoragePoolsList from './StoragePoolsList.svelte';
  import { COMPUTE_COLUMNS, BLOCK_STORAGE_COLUMNS, SHARED_FS_COLUMNS, ORCHESTRATION_COLUMNS, CONTAINER_COLUMNS, CONTAINER_INFRA_COLUMNS } from './serviceColumns.js';
  let { activeTab, computeServices, blockStorageServices, networkAgents, sharedFsServices, orchestrationServices, containerServices, magnumServices, endpoints, storagePools, loadingMap }: {
    activeTab: TabKey; computeServices: Service[]; blockStorageServices: Service[]; networkAgents: NetworkAgent[];
    sharedFsServices: Service[]; orchestrationServices: Service[]; containerServices: Service[]; magnumServices: Service[];
    endpoints: EndpointGroup[]; storagePools: StoragePool[]; loadingMap: Record<TabKey, boolean>;
  } = $props();
  const serviceTabs = $derived([
    { key: 'compute' as const, rows: computeServices, columns: COMPUTE_COLUMNS, empty: t('services.panel.noData') },
    { key: 'block_storage' as const, rows: blockStorageServices, columns: BLOCK_STORAGE_COLUMNS, empty: t('services.panel.noData') },
    { key: 'shared_file_system' as const, rows: sharedFsServices, columns: SHARED_FS_COLUMNS, empty: t('services.panel.manilaUnavailable') },
    { key: 'orchestration' as const, rows: orchestrationServices, columns: ORCHESTRATION_COLUMNS, empty: t('services.panel.heatUnavailable') },
    { key: 'container' as const, rows: containerServices, columns: CONTAINER_COLUMNS, empty: t('services.panel.zunUnavailable') },
    { key: 'container_infra' as const, rows: magnumServices, columns: CONTAINER_INFRA_COLUMNS, empty: t('services.panel.magnumUnavailable') },
  ]);
</script>

<div data-tour="admin-system-panel">
  {#if !loadingMap[activeTab]}<span class="sr-only" data-tour="admin-system-panel-ready">{t('services.panel.ready')}</span>{/if}
  {#key JSON.stringify([$auth.userId, $auth.projectId])}
    {#each serviceTabs as tab (tab.key)}
      <div hidden={activeTab !== tab.key}>
        <ServiceTable services={tab.rows} columns={tab.columns} loading={loadingMap[tab.key]} emptyMessage={tab.empty} />
      </div>
    {/each}
    <div hidden={activeTab !== 'network'}><NetworkAgentTable agents={networkAgents} loading={loadingMap.network} emptyMessage={t('services.panel.noData')} /></div>
    <div hidden={activeTab !== 'endpoints'}><EndpointsTable {endpoints} loading={loadingMap.endpoints} emptyMessage={t('services.panel.endpointsUnavailable')} /></div>
    <div hidden={activeTab !== 'storage_pools'}><StoragePoolsList pools={storagePools} loading={loadingMap.storage_pools} emptyMessage={t('services.panel.poolsUnavailable')} /></div>
  {/key}
</div>
