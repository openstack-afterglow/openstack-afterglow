<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import { projectNames } from '$lib/stores/projectNames';
	import type { AdminVolumeDetail } from '$lib/types/volume';
	import AdminVolumeDetailHeader from '$lib/components/admin/volumes/id/AdminVolumeDetailHeader.svelte';
	import AdminVolumeInfoCards from '$lib/components/admin/volumes/id/AdminVolumeInfoCards.svelte';
	import AdminVolumeAttachmentTable from '$lib/components/admin/volumes/id/AdminVolumeAttachmentTable.svelte';
	import AdminVolumeMetadataCard from '$lib/components/admin/volumes/id/AdminVolumeMetadataCard.svelte';
	import AdminVolumeExtendModal from '$lib/components/admin/volumes/id/AdminVolumeExtendModal.svelte';
	import AdminVolumeResetStatusModal from '$lib/components/admin/volumes/id/AdminVolumeResetStatusModal.svelte';
	import { toast } from '$lib/stores/toast';

	const volumeId = $derived($page.params.id);
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let volume = $state<AdminVolumeDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let deleting = $state(false);
	let showReset = $state(false);
	let resetting = $state(false);
	let showExtend = $state(false);
	let extending = $state(false);

	async function fetchVolume() {
		if (!volumeId) return;
		try {
			volume = await api.get<AdminVolumeDetail>(`/api/v1/admin/volumes/${volumeId}`, token, projectId);
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? t('volumeDetail.lookupFailed', { status: e.status }) : t('volumeDetail.serverError');
		} finally {
			loading = false;
		}
	}

	async function deleteVolume() {
		if (!volume || !await confirmDialog(t('volumeDetail.deleteConfirm', { name: volume.name || volume.id }))) return;
		deleting = true;
		try {
			await api.delete(`/api/v1/admin/volumes/${volumeId}`, token, projectId);
			goto('/admin/volumes');
		} catch (e) {
			toast.error(t('volumeDetail.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
			deleting = false;
		}
	}

	async function resetVolumeStatus(status: string): Promise<boolean> {
		resetting = true;
		try {
			await api.post(`/api/v1/admin/volumes/${volumeId}/reset-status`, { status }, token, projectId);
			showReset = false;
			await fetchVolume();
			return true;
		} catch (e) {
			toast.error(t('volumeDetail.resetFailed', { error: e instanceof ApiError ? e.message : String(e) }));
			return false;
		} finally {
			resetting = false;
		}
	}

	async function extendVolume(newSize: number): Promise<boolean> {
		if (!volume || newSize <= volume.size) {
			toast.warning(t('volumeDetail.sizeValidation'));
			return false;
		}
		extending = true;
		try {
			await api.post(`/api/v1/admin/volumes/${volumeId}/extend`, { new_size: newSize }, token, projectId);
			showExtend = false;
			await fetchVolume();
			return true;
		} catch (e) {
			toast.error(t('volumeDetail.extendFailed', { error: e instanceof ApiError ? e.message : String(e) }));
			return false;
		} finally {
			extending = false;
		}
	}

	$effect(() => {
		if (!$auth.projectId || !volumeId) return;
		loading = true;
		untrack(() => { fetchVolume(); projectNames.load(token, projectId); });
	});
</script>

<div class="p-4 md:p-8 max-w-4xl">
	<div class="flex items-center gap-3 mb-6">
		<a href="/admin/volumes" class="text-ink-2 hover:text-ink-0 text-sm transition-colors">{t('volumeDetail.back')}</a>
	</div>
	{#if loading}
		<div class="space-y-4" role="status" aria-busy="true" aria-label={t('volumeDetail.loadingInfo')}>
			<div class="h-8 motion-skeleton rounded w-64"></div>
			<div class="h-40 motion-skeleton rounded"></div>
		</div>
	{:else if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{error}</div>
	{:else if volume}
		<AdminVolumeDetailHeader {volume} {deleting} onExtend={() => { showExtend = true; }} onResetStatus={() => { showReset = true; }} onDelete={deleteVolume} />
		<AdminVolumeInfoCards {volume} />
		<AdminVolumeAttachmentTable attachments={volume.attachments} />
		<AdminVolumeMetadataCard metadata={volume.metadata} />
	{/if}
</div>

<AdminVolumeExtendModal bind:open={showExtend} currentSize={volume?.size ?? 0} {extending} onExtend={extendVolume} />
<AdminVolumeResetStatusModal bind:open={showReset} {resetting} onReset={resetVolumeStatus} />
