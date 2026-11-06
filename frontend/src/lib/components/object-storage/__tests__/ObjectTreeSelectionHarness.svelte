<script lang="ts">
	import { onMount } from 'svelte';
	import ObjectTreeTable from '../ObjectTreeTable.svelte';
	import { createObjectBrowserStore, provideObjectBrowser, type ObjectBrowserStore } from '$lib/stores/objectBrowser.svelte';

	let {
		initialSelected = [],
		filterText = '',
		onstore,
	}: {
		initialSelected?: string[];
		filterText?: string;
		onstore?: (store: ObjectBrowserStore) => void;
	} = $props();

	const store = createObjectBrowserStore({
		mode: () => 'user',
		containerName: () => 'sample-artifacts',
		token: () => undefined,
		projectId: () => 'project-a',
		ownerKey: () => 'selection-fixture-owner',
	});
	provideObjectBrowser(store);

	onMount(async () => {
		await store.load();
		store.filterText = filterText;
		store.selected = new Set(initialSelected);
		onstore?.(store);
	});
</script>

<ObjectTreeTable />
<output data-testid="selected-names">{[...store.selected].join(',')}</output>
