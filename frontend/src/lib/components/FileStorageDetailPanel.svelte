<script lang="ts">
	import { t } from '$lib/i18n/ns/file-storage';
	import { auth } from '$lib/stores/auth';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createCoalescedRefresh, type CoalescedRefresh } from '$lib/utils/coalescedRefresh';
	import { createFileStorageDetailController, provideFileStorageDetailController } from '$lib/stores/fileStorageDetailController.svelte';
	import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
	import FileStorageDetailHeader from '$lib/components/file-storage/FileStorageDetailHeader.svelte';
	import FileStorageInfoSection from '$lib/components/file-storage/FileStorageInfoSection.svelte';
	import FileStorageExportLocationsSection from '$lib/components/file-storage/FileStorageExportLocationsSection.svelte';
	import FileStorageAccessRulesSection from '$lib/components/file-storage/FileStorageAccessRulesSection.svelte';
	import FileStorageMetadataSection from '$lib/components/file-storage/FileStorageMetadataSection.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { beginExperienceAction, experienceApplied, experienceState } from '$lib/utils/experience';
	import { untrack } from 'svelte';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import type { TableViewState } from '$lib/utils/tableView.svelte';

	interface Props {
		fileStorageId: string;
		onClose?: () => void;
		onDeleted?: () => void;
	}

	let { fileStorageId, onClose, onDeleted }: Props = $props();

	let refresh!: CoalescedRefresh;
	let refreshing = $state(false);
	let accessSearch = $state('');
	let metadataSearch = $state('');
	const accessTableState = $state<TableViewState>({ sort: null, filters: {} });
	const metadataTableState = $state<TableViewState>({ sort: null, filters: {} });
	function resetTableState() {
		accessSearch = ''; metadataSearch = '';
		accessTableState.sort = null; accessTableState.filters = {};
		metadataTableState.sort = null; metadataTableState.filters = {};
	}
	let tableOwner = '';
	$effect(() => authDisplayContext.subscribe(({ key }) => {
		if (tableOwner === key) return;
		tableOwner = key;
		untrack(resetTableState);
	}));
	$effect(() => { void fileStorageId; untrack(resetTableState); });
	let experienceLive = true;
	const s = createFileStorageDetailController({
		fileStorageId: () => fileStorageId,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
		onDeleted: () => onDeleted?.(),
		onClose: () => onClose?.(),
		onMutated: () => refresh.invalidate(),
	});
	refresh = createCoalescedRefresh(async (force) => {
		refreshing = true;
		try {
			await s.fetchAll(force ? { refresh: true } : undefined);
		} finally {
			refreshing = false;
		}
	});
	$effect(() => () => { experienceLive = false; refresh.dispose(); });
	provideFileStorageDetailController(s);

	const ar = createAutoRefresh(() => refresh.run(false), {
		storageKey: 'file-storage-detail-panel',
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});

	$effect(() => {
		if (fileStorageId && $auth.token) void refresh.run(false);
	});
	async function manualRefresh() {
		const experience = beginExperienceAction('file_storage', 'refresh', 'resource.detail');
		const resource = fileStorageId, projectId = $auth.projectId, userId = $auth.userId;
		await refresh.run(true);
		experienceState(experience, s.error ? 'error' : s.fileStorage ? 'ready' : 'empty');
		if (experience) {
			const assigned = s.fileStorage;
			void experienceApplied(experience, { transport: 'shared' }, () => experienceLive && !refreshing
				&& fileStorageId === resource && $auth.projectId === projectId && $auth.userId === userId && s.fileStorage === assigned);
		}
	}
</script>

<div class="flex min-h-full flex-col {s.loading && !s.fileStorage ? '' : 'p-6'}">
	<FileStorageDetailHeader {onClose} {ar} {refreshing} onManualRefresh={manualRefresh} />

	{#if s.error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{s.error}</div>
	{:else if s.loading && !s.fileStorage}
		<LoadingState variant="surface" label={t('detail.loading')} />
	{:else if s.fileStorage}
		<div class="motion-stagger">
			<DetailHeader title={s.fileStorage.name || s.fileStorage.id} status={s.fileStorage.status}>
				{#snippet meta()}
					<span class="px-1.5 py-0.5 bg-purple-900/40 text-purple-300 rounded text-xs">{s.fileStorage!.share_proto}</span>
				{/snippet}
				{#snippet actions()}
					<button
						onclick={() => s.deleteFileStorage()}
						disabled={s.deleting}
						class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
					>
						{#if s.deleting}<LoadingState variant="control" label="" />{/if}{s.deleting ? t('actions.deleting') : t('actions.delete')}
					</button>
				{/snippet}
			</DetailHeader>

			<FileStorageInfoSection />
			{#if (s.fileStorage.export_location_details?.length ?? 0) > 0 || s.fileStorage.export_locations.length > 0}<FileStorageExportLocationsSection />{/if}
			<FileStorageAccessRulesSection tableState={accessTableState} bind:search={accessSearch} />
			<FileStorageMetadataSection tableState={metadataTableState} bind:search={metadataSearch} />
		</div>
	{/if}
</div>
