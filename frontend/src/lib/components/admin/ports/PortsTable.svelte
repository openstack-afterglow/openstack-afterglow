<script lang="ts">
	import { projectNames } from '$lib/stores/projectNames';
	import type { PortInfo } from '$lib/types/networks';
	import Pagination from '$lib/components/ui/Pagination.svelte';

	let {
		ports,
		markerStack,
		nextMarker,
		onEdit,
		onDelete,
		onPrev,
		onNext,
		onintent,
	}: {
		ports: PortInfo[];
		markerStack: string[];
		nextMarker: string | null;
		onEdit: (port: PortInfo) => void;
		onDelete: (port: PortInfo) => void;
		onPrev: () => void;
		onNext: () => void;
		onintent?: () => void;
	} = $props();
</script>

<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-4">이름/ID</th>
				<th class="text-left py-2 pr-4">상태</th>
				<th class="text-left py-2 pr-4">Device Owner</th>
				<th class="text-left py-2 pr-4">IP 주소</th>
				<th class="text-left py-2 pr-4">프로젝트</th>
				<th class="text-left py-2">액션</th>
			</tr>
		</thead>
		<tbody>
			{#each ports as p (p.id)}
				<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors">
					<td class="py-2 pr-4">
						<div class="text-ink-0 max-md:max-w-[66vw] max-md:truncate" title={p.name || ''}>{p.name || '-'}</div>
						<div class="text-ink-3 font-mono">{p.id.slice(0, 12)}...</div>
					</td>
					<td class="py-2 pr-4 {p.status === 'ACTIVE' ? 'text-green-400' : 'text-ink-2'}">{p.status}</td>
					<td class="py-2 pr-4 text-ink-3 text-xs break-all max-w-[160px]">{p.device_owner || '-'}</td>
					<td class="py-2 pr-4 font-mono text-ink-2">
						{#each p.fixed_ips as ip}
							<div>{ip.ip_address}</div>
						{/each}
						{#if p.fixed_ips.length === 0}-{/if}
					</td>
					<td class="py-2 pr-4 text-ink-3">{p.project_id ? ($projectNames.get(p.project_id) ?? p.project_id.slice(0, 8)) : '-'}</td>
					<td class="py-2">
						{#if !p.device_owner || p.device_owner === ''}
							<div class="flex items-center gap-1">
								<button
									onclick={() => onEdit(p)}
									class="px-2 py-0.5 text-xs bg-surface-selected hover:bg-surface-selected text-ink-2 rounded"
								>수정</button>
								<button
									onclick={() => onDelete(p)}
									class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded"
								>삭제</button>
							</div>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
<Pagination
	page={markerStack.length + 1}
	hasPrev={markerStack.length > 0}
	hasNext={!!nextMarker}
	note="{ports.length}개 포트"
	{onPrev}
	{onNext}
	{onintent}
/>
