<script lang="ts">
	import { createAdminVolumeDetailController, provideAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';
	import AdminVolumeDetailHeader from '$lib/components/admin-volume/AdminVolumeDetailHeader.svelte';
	import AdminVolumeStatusBar from '$lib/components/admin-volume/AdminVolumeStatusBar.svelte';
	import AdminVolumeDeleteDiagnosticSection from '$lib/components/admin-volume/AdminVolumeDeleteDiagnosticSection.svelte';
	import AdminVolumeBasicInfoSection from '$lib/components/admin-volume/AdminVolumeBasicInfoSection.svelte';
	import AdminVolumePropertiesSection from '$lib/components/admin-volume/AdminVolumePropertiesSection.svelte';
	import AdminVolumeAttachmentsSection from '$lib/components/admin-volume/AdminVolumeAttachmentsSection.svelte';
	import AdminVolumeMetadataSection from '$lib/components/admin-volume/AdminVolumeMetadataSection.svelte';

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
			<div class="text-ink-3 text-sm">로딩 중...</div>
		{:else if s.error}
			<div class="text-red-400 text-sm">{s.error}</div>
		{:else if s.volume}
			<AdminVolumeStatusBar />
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
		{/if}
	</div>
</div>
