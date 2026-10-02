<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import RichText from '$lib/i18n/RichText.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { useRouterDetailController } from '$lib/stores/routerDetailController.svelte';

	const s = useRouterDetailController();
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<div class="flex items-center justify-between mb-3">
		<h4 class="font-semibold text-ink-0 text-sm">{t('router.gateway.title')}</h4>
		{#if s.canManageRouter}
			<div class="flex gap-2">
				{#if s.router!.external_gateway_network_id}
					<button
						onclick={() => s.removeGateway()}
						disabled={s.saving}
						class="text-red-400 hover:text-red-300 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
					>{t('router.gateway.remove')}</button>
				{:else}
					<button
						onclick={() => s.showSetGateway = !s.showSetGateway}
						class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
					>{t('router.gateway.set')}</button>
				{/if}
			</div>
		{/if}
	</div>

	{#if s.router!.external_gateway_network_id}
		<div class="text-sm">
			<span class="text-ink-2"><RichText segments={t.rich('router.gateway.network', { name: s.router!.external_gateway_network_name || s.router!.external_gateway_network_id })} tags={{ network: networkName }} /></span>
			{#snippet networkName(text: string)}<span class="text-orange-300">{text}</span>{/snippet}
		</div>
	{:else}
		<p class="text-sm text-ink-2">{t('router.gateway.empty')}</p>
	{/if}

	{#if s.showSetGateway}
		<div class="mt-4 flex gap-2">
			<select bind:value={s.selectedExtNetId} class="flex-1 bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
				<option value="">{t('router.gateway.selectNetwork')}</option>
				{#each s.externalNetworks as net}
					<option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
				{/each}
			</select>
			<Button onclick={() => s.setGateway()} disabled={!s.selectedExtNetId || s.saving} size="sm">{t('router.actions.set')}</Button>
			<button onclick={() => s.showSetGateway = false} class="text-ink-2 hover:text-ink-1 text-sm px-2">{t('router.actions.cancel')}</button>
		</div>
	{/if}
</section>
