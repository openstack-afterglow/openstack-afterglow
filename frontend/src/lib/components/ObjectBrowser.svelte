<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { createObjectBrowserStore, provideObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import UploadModal from '$lib/components/UploadModal.svelte';
	import ObjectDragOverlay from '$lib/components/object-storage/ObjectDragOverlay.svelte';
	import ObjectBrowserHeader from '$lib/components/object-storage/ObjectBrowserHeader.svelte';
	import ObjectBrowserToolbar from '$lib/components/object-storage/ObjectBrowserToolbar.svelte';
	import ObjectBulkActionBar from '$lib/components/object-storage/ObjectBulkActionBar.svelte';
	import ObjectFlatTable from '$lib/components/object-storage/ObjectFlatTable.svelte';
	import ObjectTreeTable from '$lib/components/object-storage/ObjectTreeTable.svelte';
	import ObjectMetaPanel from '$lib/components/object-storage/ObjectMetaPanel.svelte';
	import ObjectTrashView from '$lib/components/object-storage/ObjectTrashView.svelte';
	import ObjectCardGrid from '$lib/components/object-storage/ObjectCardGrid.svelte';
	import ObjectPreviewModal from '$lib/components/object-storage/ObjectPreviewModal.svelte';
	import NewDirModal from '$lib/components/object-storage/NewDirModal.svelte';
	import RenameModal from '$lib/components/object-storage/RenameModal.svelte';
	import MoveModal from '$lib/components/object-storage/MoveModal.svelte';
	import { PageShell, Tabs } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/object-storage';
	import { createArrivals } from '$lib/components/object-storage/arrivals';

	interface Props {
		mode: 'user' | 'admin';
		containerName: string;
		token: string | undefined;
		projectId: string | undefined;
	}

	let { mode, containerName, token, projectId }: Props = $props();

	let showTrash = $state(false);
	const gridArrivals = createArrivals();
	const flatArrivals = createArrivals();
	const treeArrivals = createArrivals();
	let arrivalContainer = untrack(() => containerName);
	let arrivalProject = untrack(() => projectId);
	$effect.pre(() => {
		if (containerName === arrivalContainer && projectId === arrivalProject) return;
		arrivalContainer = containerName;
		arrivalProject = projectId;
		gridArrivals.reset();
		flatArrivals.reset();
		treeArrivals.reset();
	});

	const s = createObjectBrowserStore({
		mode: () => mode,
		containerName: () => containerName,
		token: () => token,
		projectId: () => projectId,
	});
	provideObjectBrowser(s);
	onDestroy(() => s.disposeThumbnails());

	const storageKey = untrack(() => mode === 'user' ? 'object-browser-user' : 'object-browser-admin');

	const ar = createAutoRefresh(
		() => {
			if (s.loading) return;
			return mode === 'user' ? s.refreshAll({ silent: true }) : s.load({ silent: true });
		},
		{ storageKey, defaultActive: true, defaultInterval: 15, intervalOptions: [10, 15, 30, 60], invokeOnMount: false }
	);

	function onManualRefresh() {
		if (mode === 'user') {
			s.refreshAll();
			s.loadContainerMeta();
		} else s.load();
	}

	function onUploadSuccess() {
		return mode === 'user' ? s.refreshAll({ silent: true }) : s.load({ silent: true });
	}

	function hasFiles(e: DragEvent): boolean {
		const types = e.dataTransfer?.types;
		if (!types) return false;
		for (let i = 0; i < types.length; i++) if (types[i] === 'Files') return true;
		return false;
	}

	// While the upload dialog is open it owns drag-and-drop: the page overlay stays hidden and a
	// drop bubbling up from the dialog is not enqueued twice. preventDefault still runs so a file
	// dropped beside the dialog never makes the browser navigate to it.
	function onWindowDragEnter(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		if (s.showUpload) return;
		s.dragActive = true;
	}
	function onWindowDragOver(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		if (s.showUpload) return;
		s.dragActive = true;
	}
	function onWindowDragLeave(e: DragEvent) {
		if (!hasFiles(e)) return;
		if (e.clientX <= 0 || e.clientY <= 0 || e.clientX >= window.innerWidth || e.clientY >= window.innerHeight) {
			s.dragActive = false;
		}
	}
	function onWindowDrop(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		s.dragActive = false;
		if (s.showUpload) return;
		s.handleDrop(e);
	}
</script>

<svelte:window
	ondragenter={onWindowDragEnter}
	ondragover={onWindowDragOver}
	ondragleave={onWindowDragLeave}
	ondrop={onWindowDrop}
/>

<ObjectDragOverlay />

<PageShell class={mode === 'user' ? 'bulk-selection-page space-y-4' : 'space-y-4'}>
	<ObjectBrowserHeader />
	<Tabs
		id="object-browser-tabs"
		value={showTrash ? 'trash' : 'files'}
		items={[
			{ value: 'files', label: t('browser.files'), panelId: 'object-files-panel' },
			{ value: 'trash', label: t('browser.trash'), panelId: 'object-trash-panel' },
		]}
		onchange={(next) => {
			showTrash = next === 'trash';
			s.selected = new Set();
		}}
		ariaLabel={t('browser.viewLabel')}
	/>

	{#if showTrash}
		<div id="object-trash-panel" role="tabpanel" aria-labelledby="object-browser-tabs-trash" tabindex="0">
		<ObjectTrashView {containerName} {token} {projectId} selectionEnabled={mode === 'user'} />
		</div>
	{:else}
		<div id="object-files-panel" role="tabpanel" aria-labelledby="object-browser-tabs-files" tabindex="0">
		<ObjectBrowserToolbar {ar} {onManualRefresh} />
		<ObjectBulkActionBar {mode} />

		{#if s.showUpload}
			<UploadModal
				{containerName}
				prefix={s.prefix}
				{token}
				{projectId}
				onSuccess={onUploadSuccess}
				onClose={() => { s.showUpload = false; }}
			/>
		{/if}

		<NewDirModal />
		<RenameModal />
		<MoveModal />
		<MoveModal bulk />
		<ObjectPreviewModal />

		<div class="flex flex-col gap-4 lg:flex-row lg:gap-6">
			<div class="flex-1 min-w-0 relative">
				{#if mode !== 'user'}
					<ObjectFlatTable arrivals={flatArrivals} />
				{:else if s.viewMode === 'grid'}
					<ObjectCardGrid arrivals={gridArrivals} />
				{:else}
					<ObjectTreeTable arrivals={treeArrivals} />
				{/if}
			</div>
			<ObjectMetaPanel />
		</div>
		</div>
	{/if}
</PageShell>
