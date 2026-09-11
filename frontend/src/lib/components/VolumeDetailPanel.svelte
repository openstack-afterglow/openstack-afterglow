<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { createVolumeDetailController, provideVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import VolumeDetailHeader from '$lib/components/volume/VolumeDetailHeader.svelte';
	import VolumeInfoCard from '$lib/components/volume/VolumeInfoCard.svelte';
	import VolumeAttachmentsList from '$lib/components/volume/VolumeAttachmentsList.svelte';
	import VolumeSnapshotsSection from '$lib/components/volume/VolumeSnapshotsSection.svelte';
	import VolumeActions from '$lib/components/volume/VolumeActions.svelte';
	import VolumeAttachModal from '$lib/components/volume/VolumeAttachModal.svelte';
	import { betaFeatures } from '$lib/stores/betaFeatures';

	interface Props {
		volumeId: string;
		onClose?: () => void;
		onDeleted?: () => void;
	}

	let { volumeId, onClose, onDeleted }: Props = $props();

	const s = createVolumeDetailController({
		volumeId: () => volumeId,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
		onDeleted: () => onDeleted?.(),
		onClose: () => onClose?.(),
		volumeSnapshotsEnabled: () => $betaFeatures.volumeSnapshots,
	});
	provideVolumeDetailController(s);

	const ar = createAutoRefresh(() => s.loadAll(), {
		storageKey: 'volume-detail-panel',
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		if (!volumeId || !$auth.token) return;
		s.reset();
		s.loadAll();
	});
</script>

<div class="p-6">
	<VolumeDetailHeader {ar} {onClose} />

	{#if s.loading}
		<div class="space-y-3">
			{#each [1, 2, 3] as _}
				<div class="h-12 bg-surface-sunken rounded-lg animate-pulse"></div>
			{/each}
		</div>
	{:else if s.error}
		<div class="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded-lg px-4 py-3">{s.error}</div>
	{:else if s.volume}
		<VolumeInfoCard />
		<VolumeAttachmentsList />
		{#if $betaFeatures.volumeSnapshots}<VolumeSnapshotsSection />{/if}
		<VolumeActions />
	{/if}
</div>

{#if s.showAttachModal}
	<VolumeAttachModal />
{/if}
