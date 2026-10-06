<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import { t } from '$lib/i18n/ns/admin-storage';

	let {
		volumeId,
		token,
		projectId,
		onClose,
		onRefresh,
	}: {
		volumeId: string;
		token?: string;
		projectId?: string;
		onClose: () => void;
		onRefresh: () => void;
	} = $props();
</script>

<SlidePanel {onClose} ariaLabel={t('volumeDetail.ariaLabel')} width="w-full md:w-[50vw] max-w-2xl" dataTour="admin-storage-detail">
	{#await import('$lib/components/AdminVolumeDetailPanel.svelte')}
		<div class="p-6"><ActivityIndicator size="sm" label={t('volumeDetail.loading')} /></div>
	{:then { default: Panel }}
		<Panel {volumeId} {onClose} {onRefresh} {token} {projectId} />
	{:catch}
		<div class="p-6">
			<a href="/admin/volumes/{volumeId}" class="text-warm-text hover:text-warm-text-hover">{t('volumeDetail.openPage')}</a>
		</div>
	{/await}
</SlidePanel>
