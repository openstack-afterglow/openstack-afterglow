<script lang="ts">
	import type { SubnetDetail } from '$lib/types/networks';

	let {
		subnets,
		networkName,
		allowAdd,
		addingSubnet,
		addError,
		onAdd,
	}: {
		subnets: SubnetDetail[];
		networkName: string;
		allowAdd: boolean;
		addingSubnet: boolean;
		addError: string;
		onAdd: (form: { name: string; cidr: string; gateway: string; dhcp: boolean }) => Promise<boolean>;
	} = $props();

	let showSubnetForm = $state(false);
	let subnetForm = $state({ name: '', cidr: '10.0.0.0/24', gateway: '', dhcp: true });

	async function handleAdd() {
		const ok = await onAdd(subnetForm);
		if (ok) {
			showSubnetForm = false;
			subnetForm = { name: '', cidr: '10.0.0.0/24', gateway: '', dhcp: true };
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">서브넷</h2>
		{#if allowAdd}
			<button
				onclick={() => { showSubnetForm = !showSubnetForm; }}
				class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
			>
				{showSubnetForm ? '닫기' : '+ 서브넷 추가'}
			</button>
		{/if}
	</div>

	{#if showSubnetForm}
		<div class="mb-4 bg-surface-sunken rounded-lg p-4 space-y-3">
			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1">이름 (선택)
					<input
						bind:value={subnetForm.name}
						type="text"
						placeholder="my-subnet"
						class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
					/>
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">CIDR
					<input
						bind:value={subnetForm.cidr}
						type="text"
						placeholder="10.0.0.0/24"
						class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1"
					/>
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">게이트웨이 (선택)
					<input
						bind:value={subnetForm.gateway}
						type="text"
						placeholder="10.0.0.1"
						class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1"
					/>
					</label>
				</div>
				<div class="flex items-end pb-1.5">
					<label class="flex items-center gap-2 text-sm text-ink-2">
						<input type="checkbox" bind:checked={subnetForm.dhcp} class="rounded border-line-2" />
						DHCP 활성화
					</label>
				</div>
			</div>
			{#if addError}
				<p class="text-red-400 text-xs">{addError}</p>
			{/if}
			<div class="flex justify-end">
				<button
					onclick={handleAdd}
					disabled={addingSubnet}
					class="text-sm px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-action-on-warm rounded transition-colors"
				>
					{addingSubnet ? '추가 중...' : '서브넷 추가'}
				</button>
			</div>
		</div>
	{/if}

	{#if subnets.length > 0}
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					<th class="text-left py-2 pr-6">이름</th>
					<th class="text-left py-2 pr-6">CIDR</th>
					<th class="text-left py-2 pr-6">게이트웨이</th>
					<th class="text-left py-2">DHCP</th>
				</tr>
			</thead>
			<tbody>
				{#each subnets as subnet}
					<tr class="border-b border-line/50">
						<td class="py-2 pr-6 text-ink-2">{subnet.name || '-'}</td>
						<td class="py-2 pr-6 text-ink-2 font-mono text-xs">{subnet.cidr}</td>
						<td class="py-2 pr-6 text-ink-2 font-mono text-xs">{subnet.gateway_ip ?? '-'}</td>
						<td class="py-2">
							{#if subnet.dhcp_enabled}
								<span class="px-1.5 py-0.5 bg-green-900/30 text-green-400 rounded text-xs">활성</span>
							{:else}
								<span class="text-ink-3 text-xs">-</span>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{:else}
		<p class="text-sm text-ink-3">서브넷 없음</p>
	{/if}
</div>
