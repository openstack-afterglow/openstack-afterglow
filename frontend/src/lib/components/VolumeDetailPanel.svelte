<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { createVolumeDetailController, provideVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
	import type { Volume } from '$lib/types/volume';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import VolumeDetailHeader from '$lib/components/volume/VolumeDetailHeader.svelte';
	import VolumeInfoCard from '$lib/components/volume/VolumeInfoCard.svelte';
	import VolumeAttachmentsList from '$lib/components/volume/VolumeAttachmentsList.svelte';
	import VolumeSnapshotsSection from '$lib/components/volume/VolumeSnapshotsSection.svelte';
	import VolumeActions from '$lib/components/volume/VolumeActions.svelte';
	import VolumeAttachModal from '$lib/components/volume/VolumeAttachModal.svelte';
	import VolumeRenameModal from '$lib/components/volume/VolumeRenameModal.svelte';
	import { betaFeatures } from '$lib/stores/betaFeatures';

	interface Props {
		volumeId: string;
		onClose?: () => void;
		onDeleted?: () => void;
		onRenamed?: (volume: Volume) => void;
		/** Bump to reload after the volume was mutated outside this panel (e.g. list rename). */
		refreshKey?: number;
	}

	let { volumeId, onClose, onDeleted, onRenamed, refreshKey = 0 }: Props = $props();

	const s = createVolumeDetailController({
		volumeId: () => volumeId,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
		onDeleted: () => onDeleted?.(),
		onClose: () => onClose?.(),
		onRenamed: (volume) => onRenamed?.(volume),
		volumeSnapshotsEnabled: () => $betaFeatures.volumeSnapshots,
	});
	provideVolumeDetailController(s);

	const ar = createAutoRefresh(() => s.loadAll(), {
		storageKey: 'volume-detail-panel',
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
	});

	// Reset only when the displayed volume or project changes; a token rotation
	// must not blank the panel, and later refreshes pick up the new token.
	let loadedScope = '';
	$effect(() => {
		const id = volumeId;
		const token = $auth.token;
		const projectId = $auth.projectId ?? '';
		if (!id || !token) return;
		const scope = `${projectId}\u0000${id}`;
		if (scope === loadedScope) return;
		loadedScope = scope;
		untrack(() => {
			s.reset();
			void s.loadAll();
		});
	});

	let appliedRefreshKey = untrack(() => refreshKey);
	$effect(() => {
		const key = refreshKey;
		if (key === appliedRefreshKey) return;
		appliedRefreshKey = key;
		untrack(() => void s.loadAll());
	});
</script>

<div class="p-6">
	<!-- SlidePanel 안(onClose 전달)에서는 닫기를 SlidePanel 이 그린다. 단독 라우트에서만 목록 백링크를 둔다. -->
	{#if !onClose}
		<a href="/dashboard/volumes" class="mb-4 inline-block text-ink-2 hover:text-ink-1 text-sm transition-colors">← 볼륨 목록</a>
	{/if}
	<VolumeDetailHeader {ar} />

	{#if s.loading && !s.volume}
		<div class="space-y-3">
			{#each [1, 2, 3] as _}
				<div class="h-12 bg-surface-sunken rounded-lg animate-pulse"></div>
			{/each}
		</div>
	{:else}
		{#if s.error}
			<div class="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded-lg px-4 py-3 mb-4">{s.error}</div>
		{/if}
		{#if s.volume}
			<VolumeInfoCard />
			<VolumeAttachmentsList />
			{#if $betaFeatures.volumeSnapshots}<VolumeSnapshotsSection />{/if}
			<VolumeActions />
		{/if}
	{/if}
</div>

{#if s.showAttachModal}
	<VolumeAttachModal />
{/if}

{#if s.showRenameModal}
	<VolumeRenameModal
		volume={s.volume}
		onclose={() => s.closeRenameModal()}
		onrenamed={(updated) => s.applyRenamedVolume(updated)}
	/>
{/if}
