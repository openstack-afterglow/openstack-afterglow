<script lang="ts">
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
				<th class="text-left py-3 px-4 font-medium">버킷 이름</th>
				<th class="text-left py-3 px-4 font-medium">프로젝트</th>
				<th class="text-left py-3 px-4 font-medium">오브젝트 수</th>
				<th class="text-left py-3 px-4 font-medium">용량</th>
				<th class="text-right py-3 px-4 font-medium">액션</th>
			</tr>
		</thead>
		<tbody>
			{#each containers as c (c.name)}
				<BucketRow container={c} {deletingId} {onDelete} />
			{/each}
		</tbody>
	</table>
</div>
