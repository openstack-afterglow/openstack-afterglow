<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import type { SwiftContainer } from '$lib/types/common';
	import BucketRow from './BucketRow.svelte';

	let {
		containers,
		deletingId,
		refreshing,
		onDelete,
	}: {
		containers: SwiftContainer[];
		deletingId: string | null;
		refreshing: boolean;
		onDelete: (name: string) => Promise<void>;
	} = $props();
</script>

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
			{#each containers as c (c.name)}
				<BucketRow container={c} {deletingId} {onDelete} />
			{/each}
		</tbody>
	</table>
</div>
