<script lang="ts">
  import { t } from '$lib/i18n/ns/admin-ops';
  import type { Service, NetworkAgent, EndpointGroup, StoragePool, TabKey } from '$lib/types/adminServices';
  import ServiceTable from './ServiceTable.svelte';
  import NetworkAgentTable from './NetworkAgentTable.svelte';
  import EndpointsTable from './EndpointsTable.svelte';
  import StoragePoolsList from './StoragePoolsList.svelte';
  import { createServiceListState } from './serviceList';
  import {
    COMPUTE_COLUMNS,
    BLOCK_STORAGE_COLUMNS,
    SHARED_FS_COLUMNS,
    ORCHESTRATION_COLUMNS,
    CONTAINER_COLUMNS,
    CONTAINER_INFRA_COLUMNS,
  } from './serviceColumns.js';

  let {
    activeTab,
    computeServices,
    blockStorageServices,
    networkAgents,
    sharedFsServices,
    orchestrationServices,
    containerServices,
    magnumServices,
    endpoints,
    storagePools,
    loadingMap,
  }: {
    activeTab: TabKey;
    computeServices: Service[];
    blockStorageServices: Service[];
    networkAgents: NetworkAgent[];
    sharedFsServices: Service[];
    orchestrationServices: Service[];
    containerServices: Service[];
    magnumServices: Service[];
    endpoints: EndpointGroup[];
    storagePools: StoragePool[];
    loadingMap: Record<TabKey, boolean>;
  } = $props();

  const views = $state({
    compute: createServiceListState(),
    network: createServiceListState(),
    block_storage: createServiceListState(),
    shared_file_system: createServiceListState(),
    orchestration: createServiceListState(),
    container: createServiceListState(),
    container_infra: createServiceListState(),
    endpoints: createServiceListState('name'),
    storage_pools: createServiceListState(),
  });
</script>

<div data-tour="admin-system-panel">
  {#if !loadingMap[activeTab]}
    <span class="sr-only" data-tour="admin-system-panel-ready">{t('services.panel.ready')}</span>
  {/if}
{#if activeTab === 'compute'}
  <ServiceTable bind:view={views.compute} services={computeServices} columns={COMPUTE_COLUMNS} loading={loadingMap.compute} emptyMessage={t('services.panel.noData')} />
{:else if activeTab === 'network'}
  <NetworkAgentTable bind:view={views.network} agents={networkAgents} loading={loadingMap.network} emptyMessage={t('services.panel.noData')} />
{:else if activeTab === 'block_storage'}
  <ServiceTable bind:view={views.block_storage} services={blockStorageServices} columns={BLOCK_STORAGE_COLUMNS} loading={loadingMap.block_storage} emptyMessage={t('services.panel.noData')} />
{:else if activeTab === 'shared_file_system'}
  <ServiceTable bind:view={views.shared_file_system} services={sharedFsServices} columns={SHARED_FS_COLUMNS} loading={loadingMap.shared_file_system} emptyMessage={t('services.panel.manilaUnavailable')} />
{:else if activeTab === 'orchestration'}
  <ServiceTable bind:view={views.orchestration} services={orchestrationServices} columns={ORCHESTRATION_COLUMNS} loading={loadingMap.orchestration} emptyMessage={t('services.panel.heatUnavailable')} />
{:else if activeTab === 'container'}
  <ServiceTable bind:view={views.container} services={containerServices} columns={CONTAINER_COLUMNS} loading={loadingMap.container} emptyMessage={t('services.panel.zunUnavailable')} />
{:else if activeTab === 'container_infra'}
  <ServiceTable bind:view={views.container_infra} services={magnumServices} columns={CONTAINER_INFRA_COLUMNS} loading={loadingMap.container_infra} emptyMessage={t('services.panel.magnumUnavailable')} />
{:else if activeTab === 'endpoints'}
  <EndpointsTable bind:view={views.endpoints} {endpoints} loading={loadingMap.endpoints} emptyMessage={t('services.panel.endpointsUnavailable')} />
{:else if activeTab === 'storage_pools'}
  <StoragePoolsList bind:view={views.storage_pools} pools={storagePools} loading={loadingMap.storage_pools} emptyMessage={t('services.panel.poolsUnavailable')} />
{/if}
</div>
