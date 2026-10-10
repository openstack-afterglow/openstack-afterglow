<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import type { SwiftContainer } from '$lib/types/common';
	import { formatStorage } from '$lib/utils/format';

	let {
		container,
		deletingId,
		onDelete,
		entrance = null,
	}: {
		container: SwiftContainer;
		deletingId: string | null;
		onDelete: (name: string) => Promise<void>;
		/** Cascade slot when this row arrives for the first time; null renders it in place. */
		entrance?: number | null;
	} = $props();
</script>

<tr
	class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors {container.is_quarantine ? 'bg-state-warning/10' : ''} {container.is_trash ? 'bg-state-neutral/10' : ''} {container.is_deleted ? 'bg-state-danger/10' : ''}"
	class:motion-fade={entrance !== null}
	style:--motion-index={entrance}
>
	<td class="py-3 px-4">
		<a
			href="/admin/object-storage/{encodeURIComponent(container.name)}{container.project_id ? `?project_id=${encodeURIComponent(container.project_id)}` : ''}"
			class="text-indigo-400 hover:text-indigo-300 font-medium max-md:block max-md:max-w-[66vw] max-md:truncate"
			title={container.name}
		>{container.name}</a>
		{#if container.is_quarantine}
			<span
				class="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium rounded border border-action-warm bg-amber-950/50 text-warm-text"
				title={t('buckets.row.quarantineHelp')}
			>
				{t('buckets.row.quarantine')}
			</span>
		{/if}
		{#if container.is_trash}
			<span
				class="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium rounded border border-orange-800 bg-orange-950/50 text-orange-400"
				title={t('buckets.row.trashHelp')}
			>
				{t('buckets.row.trash')}
			</span>
		{/if}
		{#if container.is_deleted}
			<span
				class="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium rounded border border-red-800 bg-red-950/50 text-red-400"
				title={t('buckets.row.deletedHelp')}
			>
				{t('buckets.row.deleted')}
			</span>
		{/if}
	</td>
	<td class="py-3 px-4 text-ink-2 text-xs font-mono">
		{container.project_name || container.project_id?.slice(0, 8) || '—'}
	</td>
	<td class="py-3 px-4 text-ink-2">{container.count}</td>
	<td class="py-3 px-4 text-ink-2">{formatStorage(Math.round(container.bytes / 1073741824))}</td>
	<td class="py-3 px-4 text-right">
		<button
			onclick={(e) => { e.stopPropagation(); onDelete(container.name); }}
			disabled={deletingId === container.name}
			class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
		>{deletingId === container.name ? t('buckets.row.deleting') : t('buckets.row.delete')}</button>
	</td>
</tr>
