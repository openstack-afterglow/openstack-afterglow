<script lang="ts">
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import { page } from '$app/stores';
  import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
  import { tutorialViewport } from '$lib/tutorial/viewport';
  import { onDestroy } from 'svelte';
  import { invalidateInstanceDetailSelection } from '$lib/stores/instanceDetailController.svelte';
  const unsubscribeSelection = page.subscribe(invalidateInstanceDetailSelection);
  onDestroy(unsubscribeSelection);

  const instanceId = $derived($page.params.id!);
</script>

<PageShell>
  <!-- Route-only entry: the slide panel and admin detail reuse InstanceDetailPanel without this tour.
       Tutorials are tablet-and-up, so mobile omits the empty row and the instance name stays on top. -->
  {#if tutorialViewport.current}
    <div class="mb-3 flex justify-end">
      <TutorialStartButton tour="instance-detail-delete" compactOnMobile />
    </div>
  {/if}
  <InstanceDetailPanel {instanceId} />
</PageShell>
