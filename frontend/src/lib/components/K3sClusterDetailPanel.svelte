<script lang="ts">
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { goto } from '$app/navigation';
  import { createK3sClusterDetailController, provideK3sClusterDetailController, type ActiveTab } from '$lib/stores/k3sClusterDetailController.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import K3sClusterTabs from '$lib/components/k3s/K3sClusterTabs.svelte';
  import K3sClusterMainPanel from '$lib/components/k3s/K3sClusterMainPanel.svelte';
  import K3sClusterConfigMapsCard from '$lib/components/k3s/K3sClusterConfigMapsCard.svelte';
  import K3sClusterSecretsCard from '$lib/components/k3s/K3sClusterSecretsCard.svelte';
  import K3sClusterServicesCard from '$lib/components/k3s/K3sClusterServicesCard.svelte';
  import K3sClusterDeploymentsCard from '$lib/components/k3s/K3sClusterDeploymentsCard.svelte';
  import K3sClusterPodsCard from '$lib/components/k3s/K3sClusterPodsCard.svelte';
  import K3sNamespaceSelector from '$lib/components/k3s/K3sNamespaceSelector.svelte';
  import K3sStampedeTab from '$lib/components/k3s/K3sStampedeTab.svelte';
  import K3sInstanceViewerOverlay from '$lib/components/k3s/K3sInstanceViewerOverlay.svelte';
  import K3sCloudShellOverlay from '$lib/components/k3s/K3sCloudShellOverlay.svelte';

  interface Props {
    clusterId: string;
    onClose?: () => void;
    adminMode?: boolean;
    initialTab?: ActiveTab;
    onTabChange?: (tab: ActiveTab) => void;
  }

  let { clusterId, onClose, adminMode = false, initialTab = 'main', onTabChange }: Props = $props();

  const s = createK3sClusterDetailController({
    clusterId: () => clusterId,
    token: () => $auth.token ?? undefined,
    projectId: () => $auth.projectId ?? undefined,
    adminMode: () => adminMode,
    onClose: () => (onClose ?? (() => goto('/dashboard/drover')))(),
  });
  provideK3sClusterDetailController(s);

  // Set initial tab from URL
  $effect.pre(() => {
    s.activeTab = initialTab;
  });

  // Notify parent when tab changes (for URL sync)
  $effect(() => {
    const tab = s.activeTab;
    untrack(() => onTabChange?.(tab));
  });

  createAutoRefresh(() => untrack(() => {
    s.loadCluster();
    s.loadHealth();
  }), {
    storageKey: 'k3s-cluster-events',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 15,
    intervalOptions: [10, 15, 30, 60]
  });

  $effect(() => {
    if (!$auth.projectId || !clusterId) return;
    s.reset();
    untrack(() => s.loadCluster());
  });

  $effect(() => {
    if (s.cluster?.status === 'ACTIVE' && !s.initialCheckDone) {
      s.initialCheckDone = true;
      untrack(() => {
        s.checkKubeconfig();
        s.loadHealth();
        s.loadNamespaces();
      });
    }
  });

  // Lazy-load per tab when first activated
  $effect(() => {
    const tab = s.activeTab;
    if (!s.cluster || s.cluster.status !== 'ACTIVE') return;
    untrack(() => {
      if (tab === 'configmaps' || tab === 'secrets' || tab === 'services' || tab === 'workloads' || tab === 'pods') {
        s.loadNamespaces();
      }
    });
  });
</script>

<div class="relative h-full">
  {#if s.shellOpen}
    <K3sCloudShellOverlay />
  {/if}

  {#if s.viewingInstanceId}
    <K3sInstanceViewerOverlay />
  {/if}

  <div class="p-6">
    <div class="mb-5 flex items-center justify-between">
      <!-- SlidePanel 안에서는 닫기를 SlidePanel 이 그린다(`[data-slide-panel-close]`).
           단독 라우트에서만 목록 백링크를 둔다. -->
      {#if !onClose}
        <a href="/dashboard/drover" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">
          ← Drover
        </a>
      {/if}
    </div>

    {#if s.loading}
      <div class="animate-pulse space-y-4">
        <div class="h-8 bg-surface-sunken rounded w-64"></div>
        <div class="h-40 bg-surface-sunken rounded"></div>
      </div>
    {:else if s.error}
      <div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{s.error}</div>
    {:else if s.cluster}
      <K3sClusterTabs />

      <div
        id={`k3s-panel-${s.activeTab}`}
        role="tabpanel"
        aria-labelledby={`k3s-cluster-tabs-${s.activeTab}`}
        tabindex="0"
      >
      {#if s.activeTab === 'main'}
        <K3sClusterMainPanel />
      {:else if s.activeTab === 'configmaps'}
        <K3sNamespaceSelector />
        <K3sClusterConfigMapsCard />
      {:else if s.activeTab === 'secrets'}
        <K3sNamespaceSelector />
        <K3sClusterSecretsCard />
      {:else if s.activeTab === 'services'}
        <K3sNamespaceSelector />
        <K3sClusterServicesCard />
      {:else if s.activeTab === 'workloads'}
        <K3sNamespaceSelector />
        <K3sClusterDeploymentsCard />
      {:else if s.activeTab === 'pods'}
        <K3sNamespaceSelector />
        <K3sClusterPodsCard />
      {:else if s.activeTab === 'stampede'}
        <K3sStampedeTab />
      {/if}
      </div>
    {/if}
  </div>
</div>
