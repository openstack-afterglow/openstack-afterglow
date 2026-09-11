<script lang="ts">
	import { api } from '$lib/api/client';
	import type { RouterDetail, RouterSubnet } from '$lib/types/router';
	import type { Network } from '$lib/types/networks';

	let {
		router,
		availableNetworks,
		saving,
		token,
		projectId,
		onAdd,
		onRemove,
	}: {
		router: RouterDetail;
		availableNetworks: Network[];
		saving: boolean;
		token: string | undefined;
		projectId: string | undefined;
		onAdd: (subnetId: string) => Promise<boolean>;
		onRemove: (subnetId: string) => Promise<void>;
	} = $props();

	let showAddInterface = $state(false);
	let selectedNetId = $state('');
	let allSubnets = $state<RouterSubnet[]>([]);
	let selectedSubnetId = $state('');

	$effect(() => {
		if (!selectedNetId) { allSubnets = []; selectedSubnetId = ''; return; }
		const net = availableNetworks.find(n => n.id === selectedNetId);
		if (!net) return;
		api.get<{ subnet_details: RouterSubnet[] }>(`/api/v1/networks/${selectedNetId}`, token, projectId)
			.then(d => { allSubnets = d.subnet_details ?? []; selectedSubnetId = allSubnets[0]?.id ?? ''; })
			.catch(() => {});
	});

	async function handleAdd() {
		const ok = await onAdd(selectedSubnetId);
		if (ok) {
			showAddInterface = false;
			selectedNetId = '';
			selectedSubnetId = '';
		}
	}
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="font-semibold text-ink-0">인터페이스 ({router.interfaces.length})</h2>
		<button
			onclick={() => showAddInterface = !showAddInterface}
			class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
		>+ 인터페이스 추가</button>
	</div>

	{#if showAddInterface}
		<div class="mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg">
			<div class="flex gap-2 mb-2">
				<select bind:value={selectedNetId} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
					<option value="">네트워크 선택</option>
					{#each availableNetworks as net}
						<option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
					{/each}
				</select>
				<select bind:value={selectedSubnetId} disabled={!allSubnets.length} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1 disabled:opacity-50">
					<option value="">서브넷 선택</option>
					{#each allSubnets as subnet}
						<option value={subnet.id}>{subnet.name || subnet.cidr}</option>
					{/each}
				</select>
			</div>
			<div class="flex gap-2">
				<button
					onclick={handleAdd}
					disabled={!selectedSubnetId || saving}
					class="bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-action-on-warm text-sm px-3 py-2 rounded transition-colors"
				>추가</button>
				<button onclick={() => { showAddInterface = false; selectedNetId = ''; }} class="text-ink-2 hover:text-ink-1 text-sm px-2">취소</button>
			</div>
		</div>
	{/if}

	{#if router.interfaces.length === 0}
		<p class="text-sm text-ink-3">연결된 인터페이스가 없습니다.</p>
	{:else}
		<div class="space-y-2">
			{#each router.interfaces as iface}
				<div class="flex items-center justify-between bg-surface-sunken/50 rounded-lg px-4 py-3">
					<div class="text-sm">
						<div class="text-ink-0 font-medium">{iface.subnet_name || iface.subnet_id.slice(0, 12)}</div>
						<div class="text-ink-3 text-xs font-mono mt-0.5">{iface.ip_address}</div>
					</div>
					<button
						onclick={() => onRemove(iface.subnet_id)}
						disabled={saving}
						class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
					>제거</button>
				</div>
			{/each}
		</div>
	{/if}
</section>
