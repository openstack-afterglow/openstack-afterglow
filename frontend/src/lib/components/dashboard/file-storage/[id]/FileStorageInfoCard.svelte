<script lang="ts">
	import { t } from '$lib/i18n/ns/file-storage';
	import type { FileStorage } from '$lib/types/fileStorage';

	let { fileStorage }: { fileStorage: FileStorage } = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">{t('infoCard.title')}</h2>
	<dl class="grid grid-cols-2 gap-x-8 gap-y-3">
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">ID</dt>
			<dd class="text-sm text-ink-2 font-mono">{fileStorage.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('infoCard.size')}</dt>
			<dd class="text-sm text-ink-2">{fileStorage.size} GB</dd>
		</div>
		{#if fileStorage.library_name}
			<div>
				<dt class="text-xs text-ink-2 mb-0.5">{t('infoCard.library')}</dt>
				<dd class="text-sm text-ink-2">{fileStorage.library_name}</dd>
			</div>
			<div>
				<dt class="text-xs text-ink-2 mb-0.5">{t('infoCard.version')}</dt>
				<dd class="text-sm text-ink-2">{fileStorage.library_version ?? '-'}</dd>
			</div>
			{#if fileStorage.built_at}
				<div class="col-span-2">
					<dt class="text-xs text-ink-2 mb-0.5">{t('infoCard.builtAt')}</dt>
					<dd class="text-sm text-ink-2">{fileStorage.built_at}</dd>
				</div>
			{/if}
		{/if}
	</dl>
</div>
