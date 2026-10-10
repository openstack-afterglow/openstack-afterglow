<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import { t as tc } from '$lib/i18n/ns/common';
	import { api } from '$lib/api/client';
	import type { RouterDetail, RouterSubnet } from '$lib/types/router';
	import type { Network } from '$lib/types/networks';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';

	let {
		router,
		availableNetworks,
		saving,
		canManage = false,
		token,
		projectId,
		onAdd,
		onRemove,
	}: {
		router: RouterDetail;
		availableNetworks: Network[];
		saving: boolean;
		canManage?: boolean;
		token: string | undefined;
		projectId: string | undefined;
		onAdd: (subnetId: string) => Promise<boolean>;
		onRemove: (subnetId: string) => Promise<void>;
	} = $props();

	let showAddInterface = $state(false);
	let selectedNetId = $state('');
	let allSubnets = $state<RouterSubnet[]>([]);
	let selectedSubnetId = $state('');
	const pending = createPendingAction();
	const addingInterface = $derived(pending.isActive('add', saving));

	$effect(() => {
		if (!selectedNetId) { allSubnets = []; selectedSubnetId = ''; return; }
		const net = availableNetworks.find(n => n.id === selectedNetId);
		if (!net) return;
		api.get<{ subnet_details: RouterSubnet[] }>(`/api/v1/networks/${selectedNetId}`, token, projectId)
			.then(d => { allSubnets = d.subnet_details ?? []; selectedSubnetId = allSubnets[0]?.id ?? ''; })
			.catch(() => {});
	});

	async function handleAdd() {
		const ok = await pending.run('add', () => onAdd(selectedSubnetId));
		if (ok) {
			showAddInterface = false;
			selectedNetId = '';
			selectedSubnetId = '';
		}
	}
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="font-semibold text-ink-0"><AnimatedNumber value={router.interfaces.length} format={(value) => t('router.interfaces.title', { count: Math.round(value) })} /></h2>
		{#if canManage}
			<button
				onclick={() => showAddInterface = !showAddInterface}
				class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
			>{t('router.interfaces.addWithLabel')}</button>
		{/if}
	</div>

	{#if showAddInterface}
		<div class="motion-enter mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg">
			<div class="flex gap-2 mb-2">
				<select bind:value={selectedNetId} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
					<option value="">{t('router.interfaces.selectNetwork')}</option>
					{#each availableNetworks as net}
						<option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
					{/each}
				</select>
				<select bind:value={selectedSubnetId} disabled={!allSubnets.length} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1 disabled:opacity-50">
					<option value="">{t('router.interfaces.selectSubnet')}</option>
					{#each allSubnets as subnet}
						<option value={subnet.id}>{subnet.name || subnet.cidr}</option>
					{/each}
				</select>
			</div>
			<div class="flex gap-2">
				<button
					onclick={handleAdd}
					disabled={!selectedSubnetId || saving}
					aria-busy={addingInterface}
					class="inline-flex items-center gap-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-action-on-warm text-sm px-3 py-2 rounded transition-colors"
				>{#if addingInterface}<ActivityIndicator size="xs" tone="ink" />{/if}{addingInterface ? tc('state.processing') : t('router.interfaces.add')}</button>
				<button onclick={() => { showAddInterface = false; selectedNetId = ''; }} class="text-ink-2 hover:text-ink-1 text-sm px-2">{t('router.actions.cancel')}</button>
			</div>
		</div>
	{/if}

	{#if router.interfaces.length === 0}
		<p class="text-sm text-ink-2">{t('router.interfaces.empty')}</p>
	{:else}
		<div class="space-y-2">
			{#each router.interfaces as iface}
				{@const removing = pending.isActive(`remove:${iface.subnet_id}`, saving)}
				<div class="flex items-center justify-between bg-surface-sunken/50 rounded-lg px-4 py-3">
					<div class="text-sm">
						<div class="text-ink-0 font-medium">{iface.subnet_name || iface.subnet_id.slice(0, 12)}</div>
						<div class="text-ink-2 text-xs font-mono mt-0.5">{iface.ip_address}</div>
					</div>
					{#if canManage}
						<button
							onclick={() => pending.run(`remove:${iface.subnet_id}`, () => onRemove(iface.subnet_id))}
							disabled={saving}
							aria-busy={removing}
							class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
						>{#if removing}<ActivityIndicator size="xs" tone="danger" />{/if}{removing ? tc('state.processing') : t('router.interfaces.remove')}</button>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>
