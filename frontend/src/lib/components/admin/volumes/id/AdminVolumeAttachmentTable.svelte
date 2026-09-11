<script lang="ts">
	import type { AdminVolumeDetail } from '$lib/types/volume';

	let { attachments }: { attachments: AdminVolumeDetail['attachments'] } = $props();
</script>

{#if attachments.length > 0}
	<div class="bg-surface-base border border-line rounded-xl p-4 mb-4">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">연결 정보</h3>
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					<th class="text-left py-1.5 pr-4">인스턴스 ID</th>
					<th class="text-left py-1.5 pr-4">디바이스</th>
				</tr>
			</thead>
			<tbody>
				{#each attachments as att}
					<tr class="border-b border-line/50 text-xs">
						<td class="py-2 pr-4 font-mono text-ink-2">{att.server_id}</td>
						<td class="py-2 pr-4 text-ink-2">{att.device}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
