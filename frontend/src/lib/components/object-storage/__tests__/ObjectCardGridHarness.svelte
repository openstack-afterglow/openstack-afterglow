<script lang="ts">
	import { onMount } from 'svelte';
	import ObjectCardGrid from '../ObjectCardGrid.svelte';
	import { createObjectBrowserStore, provideObjectBrowser } from '$lib/stores/objectBrowser.svelte';

	let { filterText = '' }: { filterText?: string } = $props();

	const store = createObjectBrowserStore({
		mode: () => 'user',
		containerName: () => 'sample-artifacts',
		token: () => undefined,
		projectId: () => 'project-a',
	});
	provideObjectBrowser(store);

	onMount(async () => {
		await store.refreshAll();
		store.filterText = filterText;
	});
</script>

<ObjectCardGrid />
<output data-testid="selected-names">{[...store.selected].join(',')}</output>
<output data-testid="prefix">{store.prefix}</output>
