<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import { t as tc } from '$lib/i18n/ns/common';
	import RichText from '$lib/i18n/RichText.svelte';
	import type { RouterDetail } from '$lib/types/router';
	import type { Network } from '$lib/types/networks';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';

	let {
		router,
		externalNetworks,
		saving,
		canManage = false,
		onSet,
		onRemove,
	}: {
		router: RouterDetail;
		externalNetworks: Network[];
		saving: boolean;
		canManage?: boolean;
		onSet: (externalNetworkId: string) => Promise<boolean>;
		onRemove: () => Promise<void>;
	} = $props();
	let showSetGateway = $state(false);
	let selectedExtNetId = $state('');
	const pending = createPendingAction();
	const settingGateway = $derived(pending.isActive('set', saving));
	const removingGateway = $derived(pending.isActive('remove', saving));

	async function handleSet() {
		const ok = await pending.run('set', () => onSet(selectedExtNetId));
		if (ok) {
			showSetGateway = false;
			selectedExtNetId = '';
		}
	}
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="font-semibold text-ink-0">{t('router.gateway.title')}</h2>
		{#if canManage}
			<div class="flex gap-2">
				{#if router.external_gateway_network_id}
					<button
						onclick={() => pending.run('remove', onRemove)}
						disabled={saving}
						aria-busy={removingGateway}
						class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
					>{#if removingGateway}<ActivityIndicator size="xs" tone="danger" />{/if}{removingGateway ? tc('state.processing') : t('router.gateway.remove')}</button>
				{:else}
					<button
						onclick={() => showSetGateway = !showSetGateway}
						class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
					>{t('router.gateway.set')}</button>
				{/if}
			</div>
		{/if}
	</div>

	{#if router.external_gateway_network_id}
		<div class="text-sm">
			<span class="text-ink-2"><RichText segments={t.rich('router.gateway.network', { name: router.external_gateway_network_name || router.external_gateway_network_id })} tags={{ network: networkName }} /></span>
			{#snippet networkName(text: string)}<span class="text-orange-300">{text}</span>{/snippet}
		</div>
	{:else}
		<p class="text-sm text-ink-2">{t('router.gateway.empty')}</p>
	{/if}

	{#if showSetGateway}
		<div class="motion-enter mt-4 flex gap-2">
			<select bind:value={selectedExtNetId} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
				<option value="">{t('router.gateway.selectNetwork')}</option>
				{#each externalNetworks as net}
					<option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
				{/each}
			</select>
			<button
				onclick={handleSet}
				disabled={!selectedExtNetId || saving}
				aria-busy={settingGateway}
				class="inline-flex items-center gap-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-action-on-warm text-sm px-3 py-2 rounded transition-colors"
			>{#if settingGateway}<ActivityIndicator size="xs" tone="ink" />{/if}{settingGateway ? tc('state.processing') : t('router.actions.set')}</button>
			<button onclick={() => showSetGateway = false} class="text-ink-2 hover:text-ink-1 text-sm px-2">{t('router.actions.cancel')}</button>
		</div>
	{/if}
</section>
