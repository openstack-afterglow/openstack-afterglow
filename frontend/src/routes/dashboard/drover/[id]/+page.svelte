<script lang="ts">
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import K3sClusterDetailPanel from '$lib/components/K3sClusterDetailPanel.svelte';
  import type { ActiveTab } from '$lib/stores/k3sClusterDetailController.svelte';

  const VALID_TABS: ActiveTab[] = ['main', 'configmaps', 'secrets', 'services', 'workloads', 'pods'];

  const clusterId = $derived($page.params.id);
  const initialTab = $derived.by<ActiveTab>(() => {
    const t = $page.url.searchParams.get('tab') as ActiveTab | null;
    return t && VALID_TABS.includes(t) ? t : 'main';
  });

  function handleTabChange(tab: ActiveTab) {
    const url = new URL($page.url);
    if (tab === 'main') {
      url.searchParams.delete('tab');
    } else {
      url.searchParams.set('tab', tab);
    }
    goto(url.toString(), { replaceState: true, keepFocus: true, noScroll: true });
  }
</script>

<PageShell class="h-full">
<K3sClusterDetailPanel
  clusterId={clusterId ?? ''}
  initialTab={initialTab}
  onTabChange={handleTabChange}
/>
</PageShell>
