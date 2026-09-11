<script lang="ts">
	import type { Pool, Member } from '$lib/types/loadbalancer';

	let {
		pools,
		members,
		saving,
		selectedPoolId = $bindable<string | null>(null),
		onCreatePool,
		onDeletePool,
		onAddMember,
		onRemoveMember,
	}: {
		pools: Pool[];
		members: Member[];
		saving: boolean;
		selectedPoolId: string | null;
		onCreatePool: (form: { protocol: string; lb_algorithm: string; name: string }) => Promise<boolean>;
		onDeletePool: (id: string) => Promise<void>;
		onAddMember: (form: { address: string; protocol_port: number; weight: number; name: string }) => Promise<boolean>;
		onRemoveMember: (id: string) => Promise<void>;
	} = $props();

	let showAddPool = $state(false);
	let poolForm = $state({ protocol: 'HTTP', lb_algorithm: 'ROUND_ROBIN', name: '' });
	let showAddMember = $state(false);
	let memberForm = $state({ address: '', protocol_port: 80, weight: 1, name: '' });

	async function handleCreatePool() {
		const ok = await onCreatePool(poolForm);
		if (ok) {
			showAddPool = false;
			poolForm = { protocol: 'HTTP', lb_algorithm: 'ROUND_ROBIN', name: '' };
		}
	}

	async function handleAddMember() {
		const ok = await onAddMember(memberForm);
		if (ok) {
			showAddMember = false;
			memberForm = { address: '', protocol_port: 80, weight: 1, name: '' };
		}
	}
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="font-semibold text-ink-0">풀 ({pools.length})</h2>
		<button onclick={() => showAddPool = !showAddPool} class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors">+ 추가</button>
	</div>

	{#if showAddPool}
		<div class="mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg grid grid-cols-1 sm:grid-cols-3 gap-2">
			<input bind:value={poolForm.name} placeholder="이름 (선택)" class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1" />
			<select bind:value={poolForm.protocol} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
				{#each ['HTTP', 'HTTPS', 'TCP', 'UDP'] as p}
					<option value={p}>{p}</option>
				{/each}
			</select>
			<select bind:value={poolForm.lb_algorithm} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
				{#each ['ROUND_ROBIN', 'LEAST_CONNECTIONS', 'SOURCE_IP'] as a}
					<option value={a}>{a}</option>
				{/each}
			</select>
			<button onclick={handleCreatePool} disabled={saving} class="col-span-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-ink-0 text-sm px-3 py-2 rounded">생성</button>
			<button onclick={() => showAddPool = false} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center">취소</button>
		</div>
	{/if}

	{#if pools.length === 0}
		<p class="text-sm text-ink-3">풀이 없습니다.</p>
	{:else}
		<div class="space-y-2">
			{#each pools as pool}
				<div>
					<div
						onclick={() => selectedPoolId = selectedPoolId === pool.id ? null : pool.id}
						onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && (selectedPoolId = selectedPoolId === pool.id ? null : pool.id)}
						role="button"
						tabindex="0"
						class="flex items-center justify-between bg-surface-sunken/50 hover:bg-surface-sunken rounded-lg px-4 py-3 cursor-pointer transition-colors {selectedPoolId === pool.id ? 'border border-action-warm' : ''}"
					>
						<div class="text-sm">
							<span class="text-ink-0 font-medium">{pool.name || pool.id.slice(0, 10)}</span>
							<span class="ml-2 text-xs text-purple-300 bg-purple-900/30 px-1.5 py-0.5 rounded">{pool.protocol}</span>
							<span class="ml-2 text-xs text-ink-3">{pool.lb_algorithm}</span>
							<span class="ml-2 text-xs {pool.status === 'ACTIVE' ? 'text-green-400' : 'text-yellow-400'}">{pool.status}</span>
						</div>
						<div class="flex gap-2">
							<span class="text-xs text-ink-3">{selectedPoolId === pool.id ? '▲ 멤버 접기' : '▼ 멤버 보기'}</span>
							<button onclick={(e) => { e.stopPropagation(); onDeletePool(pool.id); }} disabled={saving} class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 transition-colors">삭제</button>
						</div>
					</div>

					{#if selectedPoolId === pool.id}
						<div class="mt-2 ml-4 bg-surface-sunken/30 rounded-lg p-4 border border-line-2">
							<div class="flex items-center justify-between mb-3">
								<span class="text-sm text-ink-2">멤버 ({members.length})</span>
								<button onclick={() => showAddMember = !showAddMember} class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors">+ 멤버 추가</button>
							</div>

							{#if showAddMember}
								<div class="mb-3 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2">
									<input bind:value={memberForm.address} placeholder="IP 주소" class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1 col-span-2" />
									<input bind:value={memberForm.protocol_port} type="number" min="1" max="65535" placeholder="포트" class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1" />
									<input bind:value={memberForm.weight} type="number" min="1" max="256" placeholder="가중치" class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1" />
									<button onclick={handleAddMember} disabled={saving || !memberForm.address} class="col-span-3 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-ink-0 text-sm px-3 py-2 rounded">추가</button>
									<button onclick={() => showAddMember = false} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center rounded border border-line-2">취소</button>
								</div>
							{/if}

							{#if members.length === 0}
								<p class="text-xs text-ink-3">멤버가 없습니다.</p>
							{:else}
								<div class="space-y-1.5">
									{#each members as member}
										<div class="flex items-center justify-between bg-surface-sunken/50 rounded px-3 py-2">
											<div class="text-xs">
												<span class="text-ink-0 font-mono">{member.address}:{member.protocol_port}</span>
												<span class="ml-2 text-ink-3">가중치 {member.weight}</span>
												<span class="ml-2 {member.status === 'ACTIVE' ? 'text-green-400' : 'text-yellow-400'}">{member.status}</span>
											</div>
											<button onclick={() => onRemoveMember(member.id)} disabled={saving} class="text-red-400 hover:text-red-300 text-xs">제거</button>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>
