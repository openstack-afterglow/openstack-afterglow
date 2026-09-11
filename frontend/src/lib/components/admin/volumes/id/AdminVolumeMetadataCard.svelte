<script lang="ts">
	import type { AdminVolumeDetail } from '$lib/types/volume';

	let { metadata }: { metadata: AdminVolumeDetail['metadata'] } = $props();
</script>

{#if Object.keys(metadata).length > 0}
	<div class="bg-surface-base border border-line rounded-xl p-4">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">메타데이터</h3>
		<dl class="space-y-1.5 text-xs">
			{#each Object.entries(metadata) as [k, v]}
				<div class="flex justify-between gap-4">
					<dt class="text-ink-2 font-mono">{k}</dt>
					<dd class="text-ink-2 font-mono text-right break-all">{v}</dd>
				</div>
			{/each}
		</dl>
	</div>
{/if}
