<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import VolumeDetailPanel from '$lib/components/VolumeDetailPanel.svelte';

	const volumeId = $derived($page.params.id ?? '');
</script>

<div class="max-w-4xl mx-auto">
	<VolumeDetailPanel {volumeId} onDeleted={() => goto('/dashboard/volumes')} />
</div>
