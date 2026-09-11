<script lang="ts">
	import { useFileStorageDetailController } from '$lib/stores/fileStorageDetailController.svelte';

	const s = useFileStorageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">메타데이터</h3>
	<table class="w-full text-sm">
		<tbody>
			{#each Object.entries(s.fileStorage!.metadata) as [k, v]}
				<tr class="border-b border-line/50">
					<td class="py-2 pr-4 text-ink-3 text-xs w-1/3">{k}</td>
					<td class="py-2 text-ink-2 font-mono text-xs break-all">{v}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
