<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import { createAdminVolumeDetailController, provideAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';
	import AdminVolumeDetailHeader from '$lib/components/admin-volume/AdminVolumeDetailHeader.svelte';
	import AdminVolumeStatusBar from '$lib/components/admin-volume/AdminVolumeStatusBar.svelte';
	import AdminVolumeDeleteDiagnosticSection from '$lib/components/admin-volume/AdminVolumeDeleteDiagnosticSection.svelte';
	import AdminVolumeBasicInfoSection from '$lib/components/admin-volume/AdminVolumeBasicInfoSection.svelte';
	import AdminVolumePropertiesSection from '$lib/components/admin-volume/AdminVolumePropertiesSection.svelte';
	import AdminVolumeAttachmentsSection from '$lib/components/admin-volume/AdminVolumeAttachmentsSection.svelte';
	import AdminVolumeMetadataSection from '$lib/components/admin-volume/AdminVolumeMetadataSection.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import AdminVolumeTransferModal from '$lib/components/admin/volumes/AdminVolumeTransferModal.svelte';
	import type { AdminVolumeDetail } from '$lib/types/volume';
	let transferVolume = $state<Pick<AdminVolumeDetail, 'id' | 'name' | 'status'> | null>(null);

	interface Props {
		volumeId: string;
		onClose?: () => void;
		onRefresh?: () => void;
		token?: string;
		projectId?: string;
	}

	let { volumeId, onClose, onRefresh, token, projectId }: Props = $props();

	const s = createAdminVolumeDetailController({
		volumeId: () => volumeId,
		token: () => token,
		projectId: () => projectId,
		onClose: () => onClose?.(),
		onRefresh: () => onRefresh?.(),
	});
	provideAdminVolumeDetailController(s);
</script>

<div class="flex flex-col h-full">
	<AdminVolumeDetailHeader {onClose} />

	<div class="flex-1 overflow-y-auto p-5 space-y-4">
		{#if s.loading}
			<ActivityIndicator label={t('volumeDetail.loading')} />
		{:else if s.error}
			<div class="text-red-400 text-sm">{s.error}</div>
		{:else if s.volume}
			<div class="motion-stagger space-y-4">
				<AdminVolumeStatusBar />
				{#if (s.volume.status === 'available' && s.volume.attachments.length === 0) || s.volume.status === 'awaiting-transfer'}
					<Button variant="outline" onclick={() => { transferVolume = { id: s.volume!.id, name: s.volume!.name, status: s.volume!.status }; }}>{t('volumeList.action.transfer')}</Button>
				{/if}
				{#if s.deleteDiagnostic || s.diagnosticLoading || s.diagnosticError || s.recoveryResult}
					<AdminVolumeDeleteDiagnosticSection />
				{/if}
				<AdminVolumeBasicInfoSection />
				<AdminVolumePropertiesSection />
				{#if s.volume.attachments.length > 0}
					<AdminVolumeAttachmentsSection />
				{/if}
				{#if Object.keys(s.volume.metadata).length > 0}
					<AdminVolumeMetadataSection />
				{/if}
			</div>
		{/if}
	</div>
</div>

{#if transferVolume}
	{#key transferVolume.id}
		<AdminVolumeTransferModal volume={transferVolume} onClose={() => { transferVolume = null; }} onSuccess={() => { void s.fetchVolume(); onRefresh?.(); }} />
	{/key}
{/if}
