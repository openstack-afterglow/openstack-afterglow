<script lang="ts">
	import type { Volume } from '$lib/types/volume';
	import VolumeTransferModal from '$lib/components/volume/VolumeTransferModal.svelte';
	import VolumeExtendModal from '$lib/components/volume/VolumeExtendModal.svelte';
	import VolumeBackupModal from '$lib/components/volume/VolumeBackupModal.svelte';
	import VolumeSnapshotModal from '$lib/components/volume/VolumeSnapshotModal.svelte';
	import VolumeRenameModal from '$lib/components/volume/VolumeRenameModal.svelte';

	let {
		transferVolumeId,
		transferVolumeName,
		showTransfer,
		transferMode = 'create',
		extendTarget,
		projectId,
		backupTarget,
		snapshotTarget,
		renameTarget,
		volumeSnapshotsEnabled = true,
		onCloseTransfer,
		onTransferred,
		onTransferChanged,
		onCloseExtend,
		onExtendSuccess,
		onCloseBackup,
		onBackupSuccess,
		onCloseSnapshot,
		onSnapshotSuccess,
		onCloseRename,
		onRenamed,
	}: {
		transferVolumeId: string;
		transferVolumeName: string;
		showTransfer: boolean;
		transferMode?: 'create' | 'receive' | 'list';
		extendTarget: Volume | null;
		projectId: string | undefined;
		backupTarget: Volume | null;
		snapshotTarget: Volume | null;
		renameTarget: Volume | null;
		volumeSnapshotsEnabled?: boolean;
		onCloseTransfer: () => void;
		onTransferred: () => void;
		onTransferChanged?: () => void;
		onCloseExtend: () => void;
		onExtendSuccess: () => void;
		onBackupSuccess?: () => void;
		onCloseBackup: () => void;
		onCloseSnapshot: () => void;
		onSnapshotSuccess: () => void;
		onCloseRename: () => void;
		onRenamed: (updated: Volume) => void;
	} = $props();
</script>

{#if showTransfer}
	<VolumeTransferModal
		volumeId={transferVolumeId}
		volumeName={transferVolumeName}
		initialMode={transferMode}
		onChanged={onTransferChanged}
		onClose={onCloseTransfer}
		onTransferred={onTransferred}
	/>
{/if}

<VolumeRenameModal
	volume={renameTarget}
	onclose={onCloseRename}
	onrenamed={onRenamed}
/>

<VolumeExtendModal
	volume={extendTarget}
	{projectId}
	onclose={onCloseExtend}
	onsuccess={onExtendSuccess}
/>

<VolumeBackupModal
	volume={backupTarget}
	onclose={onCloseBackup}
	onsuccess={onBackupSuccess ?? onCloseBackup}
/>

{#if volumeSnapshotsEnabled}
	<VolumeSnapshotModal
		volume={snapshotTarget}
		onclose={onCloseSnapshot}
		onsuccess={onSnapshotSuccess}
	/>
{/if}
