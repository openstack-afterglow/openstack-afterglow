<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';

	let { mode }: { mode: 'admin' | 'user' } = $props();
	const s = useObjectBrowser();
</script>

{#if mode === 'user'}
	<BulkSelectionOverlay
		count={s.selectedCount}
		ariaLabel={t('views.bulkActionBar.ariaLabel')}
		busy={s.bulkDeleting || s.bulkMoving}
		actions={[
			{ key: 'move', label: t('views.bulkActionBar.move'), tone: 'info', onAction: s.openBulkMove },
			{ key: 'delete', label: t('views.bulkActionBar.delete'), tone: 'danger', onAction: s.bulkDelete },
		]}
		onClear={() => { s.selected = new Set(); }}
	/>
{:else if s.selectedCount > 0}
	<div class="flex items-center gap-3 mb-3 px-3 py-2 bg-indigo-950/40 border border-indigo-800/50 rounded-lg">
		<span class="text-xs text-indigo-300">{t('views.bulkActionBar.selectedCount', { count: s.selectedCount })}</span>
		<div class="flex-1"></div>
		<button
			onclick={() => { s.selected = new Set(); }}
			class="text-xs text-ink-2 hover:text-ink-0 transition-colors"
		>{t('views.bulkActionBar.clearSelection')}</button>
		<button
			onclick={s.openBulkMove}
			class="text-xs text-ink-0 bg-indigo-700 hover:bg-indigo-600 transition-colors px-3 py-1.5 rounded border border-indigo-600"
		>{t('views.bulkActionBar.moveSelected')}</button>
		<button
			onclick={s.bulkDelete}
			disabled={s.bulkDeleting}
			class="text-xs text-ink-0 bg-red-700 hover:bg-red-600 disabled:bg-surface-selected disabled:text-ink-3 transition-colors px-3 py-1.5 rounded border border-red-600 disabled:border-line-2"
		>{s.bulkDeleting ? t('views.bulkActionBar.deleting') : t('views.bulkActionBar.deleteSelected')}</button>
	</div>
{/if}
