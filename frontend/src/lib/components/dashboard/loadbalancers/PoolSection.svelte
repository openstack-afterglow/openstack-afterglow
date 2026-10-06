<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { Pool, Member } from '$lib/types/loadbalancer';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';

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
	const pending = createPendingAction();
	const creatingPool = $derived(pending.isActive('create', saving));
	const addingMember = $derived(pending.isActive('add-member', saving));

	async function handleCreatePool() {
		const ok = await pending.run('create', () => onCreatePool(poolForm));
		if (ok) {
			showAddPool = false;
			poolForm = { protocol: 'HTTP', lb_algorithm: 'ROUND_ROBIN', name: '' };
		}
	}

	async function handleAddMember() {
		const ok = await pending.run('add-member', () => onAddMember(memberForm));
		if (ok) {
			showAddMember = false;
			memberForm = { address: '', protocol_port: 80, weight: 1, name: '' };
		}
	}
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="font-semibold text-ink-0">{t('lb.pools.title', { count: pools.length })}</h2>
		<button onclick={() => showAddPool = !showAddPool} class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors">{t('lb.actions.addWithPlus')}</button>
	</div>

	{#if showAddPool}
		<div class="motion-enter mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg grid grid-cols-1 sm:grid-cols-3 gap-2">
			<input bind:value={poolForm.name} placeholder={t('lb.form.optionalName')} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1" />
			<select bind:value={poolForm.protocol} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
				{#each ['HTTP', 'HTTPS', 'TCP', 'UDP'] as p}
					<option value={p}>{p}</option>
				{/each}
			</select>
			<select bind:value={poolForm.lb_algorithm} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
				{#each ['ROUND_ROBIN', 'LEAST_CONNECTIONS', 'SOURCE_IP'] as a}
					<option value={a}>{t('lb.algorithm.label', { algorithm: a })}</option>
				{/each}
			</select>
			<button onclick={handleCreatePool} disabled={saving} aria-busy={creatingPool} class="col-span-2 inline-flex items-center justify-center gap-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-ink-0 text-sm px-3 py-2 rounded">{#if creatingPool}<ActivityIndicator size="xs" tone="ink" />{/if}{creatingPool ? tc('state.processing') : t('lb.actions.create')}</button>
			<button onclick={() => showAddPool = false} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center">{t('lb.actions.cancel')}</button>
		</div>
	{/if}

	{#if pools.length === 0}
		<p class="text-sm text-ink-2">{t('lb.pools.empty')}</p>
	{:else}
		<div class="space-y-2">
			{#each pools as pool}
				{@const deletingPool = pending.isActive(`delete:${pool.id}`, saving)}
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
							<span class="ml-2 text-xs text-ink-2">{t('lb.algorithm.label', { algorithm: pool.lb_algorithm })}</span>
							<span class="ml-2 text-xs {pool.status === 'ACTIVE' ? 'text-green-400' : 'text-yellow-400'}">{pool.status}</span>
						</div>
						<div class="flex gap-2">
							<span class="text-xs text-ink-2">{selectedPoolId === pool.id ? t('lb.pools.collapseMembers') : t('lb.pools.showMembers')}</span>
							<button onclick={(e) => { e.stopPropagation(); void pending.run(`delete:${pool.id}`, () => onDeletePool(pool.id)); }} disabled={saving} aria-busy={deletingPool} class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 transition-colors">{#if deletingPool}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingPool ? t('network.actions.deleting') : t('lb.actions.delete')}</button>
						</div>
					</div>

					{#if selectedPoolId === pool.id}
						<div class="mt-2 ml-4 bg-surface-sunken/30 rounded-lg p-4 border border-line-2">
							<div class="flex items-center justify-between mb-3">
								<span class="text-sm text-ink-2">{t('lb.members.title', { count: members.length })}</span>
								<button onclick={() => showAddMember = !showAddMember} class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors">{t('lb.members.addWithPlus')}</button>
							</div>

							{#if showAddMember}
								<div class="motion-enter mb-3 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2">
									<input bind:value={memberForm.address} placeholder={t('lb.form.ipAddress')} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1 col-span-2" />
									<input bind:value={memberForm.protocol_port} type="number" min="1" max="65535" placeholder={t('lb.form.port')} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1" />
									<input bind:value={memberForm.weight} type="number" min="1" max="256" placeholder={t('lb.form.weight')} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1" />
									<button onclick={handleAddMember} disabled={saving || !memberForm.address} aria-busy={addingMember} class="col-span-3 inline-flex items-center justify-center gap-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-ink-0 text-sm px-3 py-2 rounded">{#if addingMember}<ActivityIndicator size="xs" tone="ink" />{/if}{addingMember ? tc('state.processing') : t('lb.actions.add')}</button>
									<button onclick={() => showAddMember = false} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center rounded border border-line-2">{t('lb.actions.cancel')}</button>
								</div>
							{/if}

							{#if members.length === 0}
								<p class="text-xs text-ink-2">{t('lb.members.empty')}</p>
							{:else}
								<div class="space-y-1.5">
									{#each members as member}
										{@const removingMember = pending.isActive(`remove:${member.id}`, saving)}
										<div class="flex items-center justify-between bg-surface-sunken/50 rounded px-3 py-2">
											<div class="text-xs">
												<span class="text-ink-0 font-mono">{member.address}:{member.protocol_port}</span>
												<span class="ml-2 text-ink-2">{t('lb.members.weight', { weight: member.weight })}</span>
												<span class="ml-2 {member.status === 'ACTIVE' ? 'text-green-400' : 'text-yellow-400'}">{member.status}</span>
											</div>
											<button onclick={() => pending.run(`remove:${member.id}`, () => onRemoveMember(member.id))} disabled={saving} aria-busy={removingMember} class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 text-xs">{#if removingMember}<ActivityIndicator size="xs" tone="danger" />{/if}{removingMember ? tc('state.processing') : t('lb.actions.remove')}</button>
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
