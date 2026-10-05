<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import { formatSize } from '$lib/utils/format';

	const s = useImageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('sizeSection.title')}</h3>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-6 gap-y-3">
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('sizeSection.size')}</dt>
			<dd class="text-sm text-ink-2">{formatSize(s.image!.size)}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('sizeSection.virtualSize')}</dt>
			<dd class="text-sm text-ink-2">{formatSize(s.image!.virtual_size)}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('sizeSection.minDisk')}</dt>
			<dd class="text-sm text-ink-2">{s.image!.min_disk} GB</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('sizeSection.minRam')}</dt>
			<dd class="text-sm text-ink-2">{s.image!.min_ram} MB</dd>
		</div>
	</dl>
</div>
