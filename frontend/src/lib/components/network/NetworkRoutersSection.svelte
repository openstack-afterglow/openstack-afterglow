<script lang="ts">
	import { useNetworkDetailController } from '$lib/stores/networkDetailController.svelte';

	const s = useNetworkDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<div class="flex items-center justify-between mb-3">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide">연결된 라우터 ({s.network!.routers.length})</h3>
		{#if s.isUserPanel}
			<button
				onclick={() => s.openRouterConnect()}
				class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
			>+ 연결</button>
		{/if}
	</div>

	{#if s.showRouterConnect && s.isUserPanel}
		<div class="mb-3 p-3 bg-surface-sunken/60 border border-line-2 rounded-lg space-y-2">
			<select bind:value={s.selectedRouterId} class="w-full bg-surface-sunken border border-line-2 rounded px-2 py-1.5 text-xs text-ink-1">
				<option value="">라우터 선택</option>
				{#each s.allRouters as r}
					<option value={r.id}>{r.name || r.id.slice(0, 12)}</option>
				{/each}
			</select>
			<select bind:value={s.selectedSubnetId} class="w-full bg-surface-sunken border border-line-2 rounded px-2 py-1.5 text-xs text-ink-1">
				<option value="">서브넷 선택</option>
				{#each s.network!.subnet_details as subnet}
					<option value={subnet.id}>
						{subnet.name || subnet.cidr}{!subnet.gateway_ip ? ' (게이트웨이 자동 생성)' : ''}
					</option>
				{/each}
			</select>
			<div class="flex gap-2">
				<button
					onclick={() => s.connectRouter()}
					disabled={!s.selectedRouterId || !s.selectedSubnetId || s.connectingRouter}
					class="bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-action-on-warm text-xs px-3 py-1.5 rounded transition-colors"
				>{s.connectingRouter ? '연결 중...' : '연결'}</button>
				<button onclick={() => s.showRouterConnect = false} class="text-ink-2 hover:text-ink-1 text-xs px-2">취소</button>
			</div>
		</div>
	{/if}

	{#if s.network!.routers.length > 0}
		<div class="space-y-2">
			{#each s.network!.routers as router}
				<div class="flex items-center justify-between py-1">
					<div>
						<div class="text-xs text-ink-0">{router.name || router.id.slice(0, 8)}</div>
						<div class="text-xs text-ink-3 font-mono">{router.id.slice(0, 12)}...</div>
					</div>
					<div class="flex items-center gap-2">
						<span class="text-xs {router.status === 'ACTIVE' ? 'text-green-400' : 'text-ink-2'}">{router.status}</span>
						{#if s.isUserPanel}
							<button
								onclick={() => s.disconnectRouter(router)}
								class="text-red-400 hover:text-red-300 text-xs px-1.5 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors"
							>해제</button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{:else if !s.showRouterConnect}
		<p class="text-xs text-ink-3">연결된 라우터가 없습니다</p>
	{/if}
</div>
