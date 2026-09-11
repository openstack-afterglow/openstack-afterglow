<script lang="ts">
	import type { AdminRouter } from '$lib/types/networks';

	let {
		routers,
		onEdit,
		onDelete,
	}: {
		routers: AdminRouter[];
		onEdit: (router: AdminRouter) => void;
		onDelete: (router: AdminRouter) => void;
	} = $props();
</script>

<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-4">이름</th>
				<th class="text-left py-2 pr-4">상태</th>
				<th class="text-left py-2 pr-4">외부 게이트웨이</th>
				<th class="text-left py-2 pr-4">연결 서브넷</th>
				<th class="text-left py-2 pr-4">프로젝트</th>
				<th class="text-left py-2">액션</th>
			</tr>
		</thead>
		<tbody>
			{#each routers as r (r.id)}
				<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors">
					<td class="py-2 pr-4 text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={r.name || r.id}>{r.name || r.id.slice(0, 8)}</span></td>
					<td class="py-2 pr-4 {r.status === 'ACTIVE' ? 'text-green-400' : 'text-ink-2'}">{r.status}</td>
					<td class="py-2 pr-4 text-ink-3 font-mono">
						{r.external_gateway_network_id ? r.external_gateway_network_id.slice(0, 8) + '...' : '-'}
					</td>
					<td class="py-2 pr-4 text-ink-3">{r.connected_subnet_ids.length}개</td>
					<td class="py-2 pr-4 text-ink-3 font-mono">{r.project_id?.slice(0, 8) ?? '-'}</td>
					<td class="py-2">
						<div class="flex items-center gap-1">
							<button onclick={() => onEdit(r)}
								class="px-2 py-0.5 text-xs bg-surface-selected hover:bg-surface-selected text-ink-2 rounded">수정</button>
							<button onclick={() => onDelete(r)}
								class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded">삭제</button>
						</div>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
