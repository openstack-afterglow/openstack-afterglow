<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import { formatIsoDateTime } from '$lib/utils/format';
	import { CompactResourceCard, ResponsiveTable } from '$lib/components/ui';

	const s = useImageDetailController();
</script>

{#snippet checksumDetails()}
	<dl class="text-xs"><dt class="text-ink-2">{t('metadataSection.checksum')}</dt><dd class="font-mono text-ink-1 break-all">{s.image!.checksum}</dd></dl>
{/snippet}

<ResponsiveTable>
	{#snippet cards()}
		<CompactResourceCard details={s.image!.checksum ? checksumDetails : undefined}>
			<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide">{t('metadataSection.title')}</h3>
			<dl class="space-y-2 text-xs">
				<div><dt class="text-ink-2">{t('metadataSection.createdAt')}</dt><dd class="text-ink-1 break-words">{formatIsoDateTime(s.image!.created_at)}</dd></div>
				<div><dt class="text-ink-2">{t('metadataSection.updatedAt')}</dt><dd class="text-ink-1 break-words">{formatIsoDateTime(s.image!.updated_at)}</dd></div>
			</dl>
		</CompactResourceCard>
	{/snippet}
<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('metadataSection.title')}</h3>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-6 gap-y-3">
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('metadataSection.createdAt')}</dt>
			<dd class="text-sm text-ink-2">{formatIsoDateTime(s.image!.created_at)}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('metadataSection.updatedAt')}</dt>
			<dd class="text-sm text-ink-2">{formatIsoDateTime(s.image!.updated_at)}</dd>
		</div>
		{#if s.image!.checksum}
			<div class="col-span-2">
				<dt class="text-xs text-ink-2 mb-0.5">{t('metadataSection.checksum')}</dt>
				<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.checksum}</dd>
			</div>
		{/if}
	</dl>
</div>
</ResponsiveTable>
