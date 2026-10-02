<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';

	const s = useAdminVolumeDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('volumeDetail.properties')}</h3>
	<dl class="space-y-2 text-xs">
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('volumeDetail.bootable')}</dt>
			<dd class="{s.volume?.bootable ? 'text-green-400' : 'text-ink-2'}">{s.volume?.bootable ? t('volumeDetail.yes') : t('volumeDetail.no')}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('volumeDetail.encrypted')}</dt>
			<dd class="{s.volume?.encrypted ? 'text-yellow-400' : 'text-ink-2'}">{s.volume?.encrypted ? t('volumeDetail.yes') : t('volumeDetail.no')}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('volumeDetail.multiattach')}</dt>
			<dd class="{s.volume?.multiattach ? 'text-warm-text' : 'text-ink-2'}">{s.volume?.multiattach ? t('volumeDetail.yes') : t('volumeDetail.no')}</dd>
		</div>
	</dl>
</div>
