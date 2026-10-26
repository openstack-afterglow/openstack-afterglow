<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import type { SwiftContainer } from '$lib/types/common';
	import BucketRow from './BucketRow.svelte';
	import { createArrivals } from '../arrivals';
 import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
 import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
 import { formatStorage } from '$lib/utils/format';

	let {
		containers,
		deletingId,
		refreshing,
		onDelete,
		canDelete,
		arrivals = createArrivals(),
	}: {
		containers: SwiftContainer[];
		deletingId: string | null;
		refreshing: boolean;
		onDelete: (container: SwiftContainer) => Promise<void>;
		canDelete: (container: SwiftContainer) => boolean;
		arrivals?: ReturnType<typeof createArrivals>;
	} = $props();

</script>

<ResponsiveTable>
 {#snippet cards()}
  {#each containers as c (`${c.project_id ?? ''}/${c.name}`)}
   <CompactResourceCard>
    <a href="/admin/object-storage/{encodeURIComponent(c.name)}{c.project_id ? `?project_id=${encodeURIComponent(c.project_id)}` : ''}" class="text-sm font-medium break-all">{c.name}</a>
    <div class="flex flex-wrap gap-2 text-xs">{#if c.is_quarantine}<span class="text-state-warning-text" title={t('buckets.row.quarantineHelp')}>{t('buckets.row.quarantine')}</span>{/if}{#if c.is_trash}<span class="text-ink-2" title={t('buckets.row.trashHelp')}>{t('buckets.row.trash')}</span>{/if}{#if c.is_deleted}<span class="text-state-danger-text" title={t('buckets.row.deletedHelp')}>{t('buckets.row.deleted')}</span>{/if}</div>
    <p class="text-xs text-ink-2 break-all">{t('buckets.table.project')}: {c.project_name || c.project_id?.slice(0, 8) || '—'}</p><p class="text-xs text-ink-2">{t('buckets.table.objectCount')}: {c.count} · {t('buckets.table.capacity')}: {formatStorage(Math.round(c.bytes / 1073741824))}</p>
    {#snippet actions()}<button onclick={() => { if (canDelete(c)) onDelete(c); }} disabled={!canDelete(c) || deletingId === `${c.project_id ?? ''}/${c.name}`} class="text-xs text-state-danger-text disabled:text-ink-3">{deletingId === `${c.project_id ?? ''}/${c.name}` ? t('buckets.row.deleting') : t('buckets.row.delete')}</button>{/snippet}
   </CompactResourceCard>
  {/each}
 {/snippet}
<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-3 px-4 font-medium">{t('buckets.table.name')}</th>
				<th class="text-left py-3 px-4 font-medium">{t('buckets.table.project')}</th>
				<th class="text-left py-3 px-4 font-medium">{t('buckets.table.objectCount')}</th>
				<th class="text-left py-3 px-4 font-medium">{t('buckets.table.capacity')}</th>
				<th class="text-right py-3 px-4 font-medium">{t('buckets.table.actions')}</th>
			</tr>
		</thead>
		<tbody>
			{#each containers as c (`${c.project_id ?? ''}/${c.name}`)}
				{@const entrance = arrivals.next(`${c.project_id ?? ''}/${c.name}`)}
				<BucketRow container={c} {deletingId} {onDelete} {canDelete} {entrance} />
			{/each}
		</tbody>
	</table>
</div>
</ResponsiveTable>
