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
		extendTarget,
		backupTarget,
		snapshotTarget,
		renameTarget,
		volumeSnapshotsEnabled = true,
		onCloseTransfer,
		onTransferred,
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
		extendTarget: Volume | null;
		backupTarget: Volume | null;
		snapshotTarget: Volume | null;
		renameTarget: Volume | null;
		volumeSnapshotsEnabled?: boolean;
		onCloseTransfer: () => void;
		onTransferred: () => void;
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
