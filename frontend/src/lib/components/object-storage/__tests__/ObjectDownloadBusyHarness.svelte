<script lang="ts">
	import ObjectCardGrid from '../ObjectCardGrid.svelte';
	import ObjectFlatTable from '../ObjectFlatTable.svelte';
	import ObjectPreviewModal from '../ObjectPreviewModal.svelte';
	import ObjectTreeTable from '../ObjectTreeTable.svelte';
	import { createObjectBrowserStore, provideObjectBrowser } from '$lib/stores/objectBrowser.svelte';

	let { view }: { view: 'tree' | 'flat' | 'grid' } = $props();

	// The store reads its mode on every request, so the admin flat table gets the blob download path.
	const store = createObjectBrowserStore({
		mode: () => (view === 'flat' ? 'admin' : 'user'),
		containerName: () => 'sample-artifacts',
		token: () => undefined,
		projectId: () => 'project-a',
	});
	provideObjectBrowser(store);
</script>

{#if view === 'flat'}
	<ObjectFlatTable />
{:else if view === 'grid'}
	<ObjectCardGrid />
{:else}
	<ObjectTreeTable />
{/if}
<ObjectPreviewModal />
<button type="button" onclick={() => store.doRefresh()}>harness refresh</button>
<button type="button" onclick={() => store.doRefresh({ silent: true })}>harness poll</button>
