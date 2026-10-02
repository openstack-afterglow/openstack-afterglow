<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';

	const s = useImageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('infoSection.title')}</h3>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-6 gap-y-3">
		<div class="col-span-2">
			<dt class="text-xs text-ink-2 mb-0.5">ID</dt>
			<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('infoSection.osDistro')}</dt>
			<dd class="text-sm text-ink-2">{s.image!.os_distro ?? '-'}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('infoSection.diskFormat')}</dt>
			<dd class="text-sm text-ink-2">{s.image!.disk_format ?? '-'}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('infoSection.containerFormat')}</dt>
			<dd class="text-sm text-ink-2">{s.image!.container_format ?? '-'}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('infoSection.protected')}</dt>
			<dd class="text-sm text-ink-2">{s.image!.protected ? t('infoSection.yes') : t('infoSection.no')}</dd>
		</div>
		{#if s.image!.tags.length > 0}
			<div class="col-span-2">
				<dt class="text-xs text-ink-2 mb-0.5">{t('infoSection.tags')}</dt>
				<dd class="text-sm text-ink-2">{s.image!.tags.join(', ')}</dd>
			</div>
		{/if}
		{#if s.isAdmin}
			<div class="col-span-2">
				<dt class="text-xs text-ink-2 mb-0.5">{t('infoSection.owner')}</dt>
				<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.owner ?? '-'}</dd>
			</div>
		{/if}
		{#if s.image!.os_hash_algo}
			<div class="col-span-2">
				<dt class="text-xs text-ink-2 mb-0.5">{t('infoSection.hash', { algorithm: s.image!.os_hash_algo })}</dt>
				<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.os_hash_value ?? '-'}</dd>
			</div>
		{/if}
		{#if s.isAdmin && s.image!.direct_url}
			<div class="col-span-2">
				<dt class="text-xs text-ink-2 mb-0.5">{t('infoSection.storageLocation')}</dt>
				<dd class="text-xs text-ink-2 font-mono break-all">{s.image!.direct_url}</dd>
			</div>
		{/if}
	</dl>
</div>
