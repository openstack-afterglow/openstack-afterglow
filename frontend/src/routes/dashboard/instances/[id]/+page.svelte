<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { page } from '$app/stores';
	import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';

	const instanceId = $derived($page.params.id!);
</script>

<PageShell>
	<InstanceDetailPanel {instanceId} />
</PageShell>
