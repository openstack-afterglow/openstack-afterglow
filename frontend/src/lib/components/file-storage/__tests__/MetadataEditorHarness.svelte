<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { createFileStorageWizardStore, provideFsWizard, type FileStorageWizardStore } from '$lib/stores/fileStorageWizardStore.svelte';
	import FileStorageWizardStep1 from '../wizard/FileStorageWizardStep1.svelte';

	let { onStore }: { onStore: (store: FileStorageWizardStore) => void } = $props();
	const store = createFileStorageWizardStore({ open: () => true, setOpen: () => {}, onCreated: () => {} });
	store.metaEntries = [{ key: 'matching', value: 'one' }, { key: 'other', value: 'two' }];
	provideFsWizard(store);
	untrack(() => onStore(store));
	onDestroy(() => store.dispose());
</script>

<FileStorageWizardStep1 />
