<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { Pool, Member } from '$lib/types/loadbalancer';
	import LbPoolMembersPanel from './LbPoolMembersPanel.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';
	import { CompactResourceCard, Button, StatusChip } from '$lib/components/ui';

	let {
		pools,
		selectedPoolId,
		members,
		membersLoading,
		saving,
		error,
		addingMember,
		addMemberError,
		onAddPool,
		onDeletePool,
		onSelectPool,
		onAddMember,
		onRemoveMember,
	}: {
		pools: Pool[];
		selectedPoolId: string | null;
		members: Member[];
		membersLoading: boolean;
		saving: boolean;
		error: string;
		addingMember: boolean;
		addMemberError: string;
		onAddPool: (form: { protocol: string; lb_algorithm: string; name: string }) => Promise<boolean>;
		onDeletePool: (id: string) => Promise<void>;
		onSelectPool: (id: string | null) => void;
		onAddMember: (form: { address: string; protocol_port: number; weight: number; name: string }) => Promise<boolean>;
		onRemoveMember: (memberId: string) => Promise<void>;
	} = $props();

	let showAddPool = $state(false);
	let poolForm = $state({ protocol: 'HTTP', lb_algorithm: 'ROUND_ROBIN', name: '' });
	const pending = createPendingAction();
	const creatingPool = $derived(pending.isActive('create', saving));

	async function handleAddPool() {
		const ok = await pending.run('create', () => onAddPool(poolForm));
		if (ok) {
			showAddPool = false;
			poolForm = { protocol: 'HTTP', lb_algorithm: 'ROUND_ROBIN', name: '' };
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
			<button onclick={handleAddPool} disabled={saving} aria-busy={creatingPool} class="sm:col-span-2 inline-flex items-center justify-center gap-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-ink-0 text-sm px-3 py-2 rounded">{#if creatingPool}<ActivityIndicator size="xs" tone="ink" />{/if}{creatingPool ? tc('state.processing') : t('lb.actions.create')}</button>
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
					<CompactResourceCard selected={selectedPoolId === pool.id}>
						<div class="flex items-center gap-2"><strong class="min-w-0 flex-1 break-all">{pool.name || pool.id.slice(0, 10)}</strong><StatusChip status={pool.status} /></div>
						<p class="text-xs text-ink-2">{pool.protocol} · {t('lb.algorithm.label', { algorithm: pool.lb_algorithm })}</p>
						{#snippet details()}<p class="font-mono break-all">ID: {pool.id}</p>{/snippet}
						{#snippet actions()}
							<Button size="sm" variant="secondary" onclick={() => onSelectPool(selectedPoolId === pool.id ? null : pool.id)} ariaExpanded={selectedPoolId === pool.id}>{selectedPoolId === pool.id ? t('lb.pools.collapseMembers') : t('lb.pools.showMembers')}</Button>
							<Button variant="danger-outline" size="sm" onclick={() => pending.run(`delete:${pool.id}`, () => onDeletePool(pool.id))} disabled={saving} ariaBusy={deletingPool}>{#if deletingPool}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingPool ? t('network.actions.deleting') : t('lb.actions.delete')}</Button>
						{/snippet}
					</CompactResourceCard>

					{#if selectedPoolId === pool.id}
						<LbPoolMembersPanel
							{members}
							{membersLoading}
							adding={addingMember}
							error={addMemberError}
							onAdd={onAddMember}
							onRemove={onRemoveMember}
						/>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>
