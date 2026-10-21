<script lang="ts">
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import { page } from '$app/stores';
  import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
  import { onDestroy } from 'svelte';
  import { invalidateInstanceDetailSelection } from '$lib/stores/instanceDetailController.svelte';
  const unsubscribeSelection = page.subscribe(invalidateInstanceDetailSelection);
  onDestroy(unsubscribeSelection);

  const instanceId = $derived($page.params.id!);
</script>

<PageShell>
  <InstanceDetailPanel {instanceId} />
</PageShell>
