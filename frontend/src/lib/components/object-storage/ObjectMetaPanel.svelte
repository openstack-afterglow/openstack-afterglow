<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';

	const s = useObjectBrowser();
</script>

{#if s.loadingMeta}
	<div class="w-72 shrink-0 bg-surface-base border border-line rounded-xl p-4">
		<LoadingSkeleton variant="detail" rows={6} />
	</div>
{:else if s.selectedMeta}
	<div class="w-72 shrink-0 bg-surface-base border border-line rounded-xl p-4 text-sm">
		<div class="flex items-center justify-between mb-3">
			<h3 class="text-ink-0 font-medium text-xs">{t('views.metaPanel.title')}</h3>
			<button onclick={() => s.selectedMeta = null} class="text-ink-2 hover:text-ink-2 text-xs">{t('views.metaPanel.closeSymbol')}</button>
		</div>
		<div class="space-y-2">
			<div>
				<div class="text-ink-2 text-xs">{t('views.metaPanel.name')}</div>
				<div class="text-ink-0 break-all">{s.selectedMeta.name}</div>
			</div>
			<div>
				<div class="text-ink-2 text-xs">{t('views.metaPanel.size')}</div>
				<div class="text-ink-0">{t('views.metaPanel.byteSize', { size: s.selectedMeta.bytes.toLocaleString(intlLocale()) })}</div>
			</div>
			<div>
				<div class="text-ink-2 text-xs">{t('views.metaPanel.contentType')}</div>
				<div class="text-ink-0">{s.selectedMeta.content_type || t('views.metaPanel.unavailable')}</div>
			</div>
			<div>
				<div class="text-ink-2 text-xs">{t('views.metaPanel.etag')}</div>
				<div class="text-ink-2 font-mono text-xs break-all">{s.selectedMeta.etag || t('views.metaPanel.unavailable')}</div>
			</div>
			{#if s.selectedMeta.sha256}
				<div>
					<div class="text-ink-2 text-xs">{t('views.metaPanel.sha256')}</div>
					<div class="text-ink-2 font-mono text-xs break-all">{s.selectedMeta.sha256}</div>
				</div>
			{/if}
			{#if s.selectedMeta.detected_content_type}
				<div>
					<div class="text-ink-2 text-xs">{t('views.metaPanel.detectedType')}</div>
					<div class="text-ink-0 text-xs">{s.selectedMeta.detected_content_type}</div>
				</div>
			{/if}
			<div>
				<div class="text-ink-2 text-xs">{t('views.metaPanel.modified')}</div>
				<div class="text-ink-0">{s.selectedMeta.last_modified ? s.selectedMeta.last_modified.slice(0, 19) : t('views.metaPanel.unavailable')}</div>
			</div>
			{#if s.selectedMeta.content_encoding}
				<div>
					<div class="text-ink-2 text-xs">{t('views.metaPanel.contentEncoding')}</div>
					<div class="text-ink-0">{s.selectedMeta.content_encoding}</div>
				</div>
			{/if}
		</div>
	</div>
{/if}
