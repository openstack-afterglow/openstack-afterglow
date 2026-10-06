<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import ObjectCardGrid from '../ObjectCardGrid.svelte';
	import { createObjectBrowserStore, provideObjectBrowser, type ObjectBrowserStore } from '$lib/stores/objectBrowser.svelte';

	let { filterText = '', onstore }: { filterText?: string; onstore?: (store: ObjectBrowserStore) => void } = $props();

	const store = createObjectBrowserStore({
		mode: () => 'user',
		containerName: () => 'sample-artifacts',
		token: () => undefined,
		projectId: () => 'project-a',
	});
	provideObjectBrowser(store);
	untrack(() => onstore?.(store));

	onMount(async () => {
		await store.refreshAll();
		store.filterText = filterText;
	});
</script>

<ObjectCardGrid />
<output data-testid="selected-names">{[...store.selected].join(',')}</output>
<output data-testid="prefix">{store.prefix}</output>
