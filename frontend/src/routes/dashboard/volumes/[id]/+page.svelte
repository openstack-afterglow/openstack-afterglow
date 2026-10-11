<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import VolumeDetailPanel from '$lib/components/VolumeDetailPanel.svelte';

	const volumeId = $derived($page.params.id ?? '');
</script>

<PageShell>
	<VolumeDetailPanel {volumeId} onDeleted={() => goto('/dashboard/volumes')} />
</PageShell>
